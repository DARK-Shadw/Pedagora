"""Teacher Agent router — WebSocket for live teaching + REST for session management."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.agents.teacher.dag_navigator import DagNavigator
from app.agents.teacher.frame_navigator import FrameNavigator
from app.agents.teacher.dialogue_state import DialogueState
from app.agents.teacher import session_manager
from app.services.agent_task import fetch_course_plan, get_lesson_animations
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── REST Endpoints ───


class CreateSessionRequest(BaseModel):
    goal_id: str
    lesson_id: str
    student_name: str = ""
    fresh: bool = False  # Force a fresh session even if one exists


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    is_resuming: bool


class ShareLinkRequest(BaseModel):
    goal_id: str
    lesson_id: str


class ShareLinkResponse(BaseModel):
    share_code: str


@router.get("/debug-auth")
async def debug_auth(token: str = Query(default="")):
    """Debug endpoint to test token validation. Remove in production."""
    if not token:
        return {"error": "No token", "token_length": 0}

    try:
        import jwt as pyjwt
        from jwt import PyJWKClient
        from app.config import get_settings
        settings = get_settings()

        jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
        jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "HS256"],
            audience="authenticated",
        )
        return {"ok": True, "sub": payload.get("sub"), "email": payload.get("email")}
    except Exception as e:
        return {"error": str(e), "token_length": len(token), "token_start": token[:20]}


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_teaching_session(
    request: CreateSessionRequest,
    user: dict = Depends(get_current_user),
):
    """Create or resume a teaching session for a lesson."""
    user_id = user["sub"]

    # Verify course plan exists
    course_plan = await fetch_course_plan(request.goal_id)
    if not course_plan:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Course plan must be completed first",
        )

    # Verify lesson exists
    lesson_plans = course_plan.get("lesson_plans", {})
    if request.lesson_id not in lesson_plans:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson '{request.lesson_id}' not found in course plan",
        )

    # Check for existing session (unless fresh requested)
    if not request.fresh:
        existing = await session_manager.find_active_session(
            request.goal_id, request.lesson_id, user_id,
        )
        if existing:
            # Kick off prefetch for the resumed session — covers sessions
            # created before the prefetch feature, and re-warms the cache
            # if the previous prefetch task was lost on backend restart.
            asyncio.create_task(
                session_manager._prefetch_session_audio(
                    session_id=existing["id"],
                    goal_id=request.goal_id,
                    lesson_id=request.lesson_id,
                    user_id=user_id,
                )
            )
            return CreateSessionResponse(
                session_id=existing["id"],
                status=existing["status"],
                is_resuming=True,
            )

    # Create new session (create_session already starts the prefetch task)
    session = await session_manager.create_session(
        goal_id=request.goal_id,
        lesson_id=request.lesson_id,
        user_id=user_id,
    )

    return CreateSessionResponse(
        session_id=session["id"],
        status="active",
        is_resuming=False,
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Get session state (for reconnection check)."""
    session = await session_manager.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("user_id") != user["sub"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return session


@router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Get post-lesson summary."""
    session = await session_manager.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session.get("status"),
        "summary": session.get("session_summary"),
        "scores": session.get("student_scores"),
    }


@router.post("/share-link", response_model=ShareLinkResponse)
async def create_share_link(
    request: ShareLinkRequest,
    user: dict = Depends(get_current_user),
):
    """Create a shareable lesson link."""
    code = await session_manager.create_share_link(
        goal_id=request.goal_id,
        lesson_id=request.lesson_id,
        user_id=user["sub"],
    )
    return ShareLinkResponse(share_code=code)


@router.get("/share/{share_code}")
async def resolve_share_link(share_code: str):
    """Resolve a share code to goal_id + lesson_id. No auth required."""
    result = await session_manager.resolve_share_link(share_code)
    if not result:
        raise HTTPException(status_code=404, detail="Share link not found or expired")
    return result


# ─── Animation Step Extraction ───


_GSAP_LABEL_RE = None


def _get_gsap_label_re():
    """Lazy-compiled regex for tl.addLabel('name', ...) extraction."""
    global _GSAP_LABEL_RE
    if _GSAP_LABEL_RE is None:
        import re
        _GSAP_LABEL_RE = re.compile(
            r"tl\.addLabel\(['\"]([^'\"]+)['\"]"
        )
    return _GSAP_LABEL_RE


def _local_animation_path(goal_id: str, lesson_id: str, frame_id: str) -> str | None:
    """Return the local generated_visuals path if it exists."""
    import os
    candidates = [
        # Test fixtures use unsuffixed paths in generated_visuals/
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "generated_visuals",
            f"{frame_id}.html",
        ),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


async def extract_animation_step_specs(
    goal_id: str,
    lesson_id: str,
    frame_id: str,
) -> list[dict]:
    """Extract GSAP step labels from an animation HTML file.

    Returns a list of [{label, anim_time}] in source order. Currently uses
    a fast regex (label names only). Absolute times default to 0.0 because
    the lockstep engine uses seekToStep(label) — it does NOT need exact
    timestamps to function.

    Returns an empty list if the file doesn't exist or has no labels.
    """
    path = _local_animation_path(goal_id, lesson_id, frame_id)
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        labels = _get_gsap_label_re().findall(html)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for label in labels:
            if label not in seen:
                seen.add(label)
                unique.append(label)
        return [{"label": label, "anim_time": 0.0} for label in unique]
    except Exception as e:
        logger.warning(f"[Teacher] step extraction failed for {frame_id}: {e}")
        return []


# ─── Animation Serving ───


@router.get("/animation/{goal_id}/{lesson_id}/{frame_id}.html")
async def serve_animation(goal_id: str, lesson_id: str, frame_id: str):
    """Serve animation HTML with correct content-type.

    Tries local file first, falls back to Supabase proxy. Sends no-cache
    headers because we iterate on these files frequently and a stale
    iframe cache produced a confusing source-code-in-iframe bug once.
    """
    import os

    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    # Try local file first (faster, no network)
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "generated_visuals",
        f"{frame_id}.html",
    )
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.lstrip().lower().startswith("<!doctype"):
            # Sanity check: an unrendered template would start with `\\` or
            # plain text. Refuse to serve so the iframe shows the fallback.
            raise HTTPException(status_code=500, detail="Animation file is not valid HTML")
        return HTMLResponse(content=content, status_code=200, headers=no_cache_headers)

    # Fallback: proxy from Supabase
    import httpx
    sb = get_supabase()
    storage_path = f"visuals/{goal_id}/{lesson_id}/{frame_id}.html"
    public_url = sb.storage.from_("animations").get_public_url(storage_path)

    async with httpx.AsyncClient() as client:
        resp = await client.get(public_url, timeout=15)
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Animation not found")
        return HTMLResponse(content=resp.text, status_code=200, headers=no_cache_headers)


# ─── WebSocket Endpoint ───


@router.websocket("/ws/teach/{session_id}")
async def teach_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
    fresh: bool = Query(default=False),
):
    """Main WebSocket for live teaching sessions.

    Frontend connects here after creating a session via REST.
    Backend navigates the teaching DAG and sends messages.
    Frontend sends student responses, reactions, and controls.
    """
    await websocket.accept()
    print(f"[TEACHER WS] Connection accepted. session_id={session_id}, token_len={len(token)}", flush=True)

    try:
        await _handle_teaching_session(websocket, session_id, token, fresh)
    except Exception as e:
        import traceback
        print(f"[TEACHER WS] FATAL ERROR: {e}", flush=True)
        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "message": str(e)[:200], "recoverable": False})
            await websocket.close(code=1011)
        except Exception:
            pass


async def _handle_teaching_session(
    websocket: WebSocket,
    session_id: str,
    token: str,
    fresh: bool,
) -> None:
    """Inner handler — separated so top-level try/except catches all errors."""

    # Auth via query param token
    user_id = None
    if token:
        try:
            import jwt as pyjwt
            from jwt import PyJWKClient
            from app.config import get_settings
            settings = get_settings()

            jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url, cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "HS256"],
                audience="authenticated",
            )
            user_id = payload.get("sub")
            print(f"[TEACHER WS] JWKS auth OK: user={user_id}", flush=True)
        except Exception as e:
            print(f"[TEACHER WS] JWKS auth failed: {e}", flush=True)
            # Fallback: try raw JWT secret (for local dev)
            try:
                from jose import jwt as jose_jwt
                from app.config import get_settings
                settings = get_settings()
                payload = jose_jwt.decode(
                    token,
                    settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated",
                )
                user_id = payload.get("sub")
                print(f"[TEACHER WS] JWT secret auth OK: user={user_id}", flush=True)
            except Exception as e2:
                print(f"[TEACHER WS] Both auth methods failed: JWKS={e}, Secret={e2}", flush=True)

    if not user_id:
        # Last resort: extract user_id from session record itself
        session = await session_manager.load_session(session_id)
        if session:
            user_id = session.get("user_id")
            print(f"[TEACHER WS] Auth bypassed — using session user_id: {user_id}", flush=True)
        else:
            await websocket.send_json({"type": "error", "message": "Authentication failed", "recoverable": False})
            await websocket.close(code=4001)
            return

    # Load session
    session = await session_manager.load_session(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": "Session not found", "recoverable": False})
        await websocket.close(code=4004)
        return

    goal_id = session["goal_id"]
    lesson_id = session["lesson_id"]

    # Load lesson plan + animations
    course_plan = await fetch_course_plan(goal_id)
    if not course_plan:
        await websocket.send_json({"type": "error", "message": "Course plan not found", "recoverable": False})
        await websocket.close(code=4004)
        return

    lesson_plan = course_plan.get("lesson_plans", {}).get(lesson_id)
    if not lesson_plan:
        await websocket.send_json({"type": "error", "message": "Lesson not found", "recoverable": False})
        await websocket.close(code=4004)
        return

    # Get animation URLs.
    #
    # We DO NOT use a.get("output_url") directly. Some rows still hold raw
    # Supabase Storage URLs from older uploads, others hold local proxy URLs.
    # The Storage copies can be stale (e.g. an unfixed f02), and serving them
    # directly bypasses our local proxy's no-cache headers + DOCTYPE sanity
    # check. Always rewrite to the local proxy route — it falls back to
    # Supabase Storage automatically if the local file is missing.
    animations = await get_lesson_animations(goal_id, lesson_id)
    proxy_base = str(websocket.url).split("/teacher/ws/")[0].replace("ws://", "http://").replace("wss://", "https://")
    animation_urls = {
        a["animation_id"]: f"{proxy_base}/teacher/animation/{goal_id}/{lesson_id}/{a['animation_id']}.html"
        for a in animations
        if a.get("status") == "completed" and a.get("animation_id")
    }

    # Load user preferences (graceful fallback if user has no onboarding data)
    teaching_style = "lecture"
    student_name = ""
    try:
        from app.services.agent_task import fetch_onboarding_data
        onboarding = await fetch_onboarding_data(goal_id, user_id)
        preferences = onboarding.get("preferences", {})
        teaching_style = preferences.get("teaching_style", "lecture")
        student_name = onboarding.get("profile", {}).get("full_name", "")
    except Exception as e:
        print(f"[TEACHER WS] Onboarding data not found, using defaults: {e}", flush=True)
        # Try to get just the profile name
        try:
            sb = get_supabase()
            profile = sb.table("profiles").select("email").eq("id", user_id).execute()
            if profile.data:
                email = profile.data[0].get("email", "")
                student_name = email.split("@")[0] if email else "Student"
        except Exception:
            student_name = "Student"

    # Load or create dialogue state
    if fresh:
        dialogue_state = DialogueState()
        print(f"[TEACHER WS] Fresh session requested — resetting dialogue state", flush=True)
    else:
        dialogue_state = DialogueState.from_dict(session.get("dialogue_state", {}))

    # Create navigator — use FrameNavigator for v2 lessons with frames,
    # fall back to DagNavigator for v1 segment-based lessons.
    frames = lesson_plan.get("frames", [])
    if frames:
        # Quick regex extraction of step labels per frame. The navigator's
        # _teach_frame will resolve text + audio lazily via the audio cache
        # (which the session_manager prefetch task is filling in the background).
        from app.services.audio_cache import get_or_create_cache

        audio_cache = await get_or_create_cache(session_id)
        frame_step_specs: dict[str, list[dict]] = {}
        for frame in frames:
            fid = frame.get("frame_id", "")
            if not fid:
                continue
            specs = await extract_animation_step_specs(goal_id, lesson_id, fid)
            if not specs:
                specs = [{"label": "main", "anim_time": 0.0}]
            frame_step_specs[fid] = specs

        navigator = FrameNavigator(
            frames=frames,
            animation_urls=animation_urls,
            lesson_title=lesson_plan.get("title", ""),
            opening_hook=lesson_plan.get("opening_hook", ""),
            closing_summary=lesson_plan.get("closing_summary", []),
            teaching_style=teaching_style,
            student_name=student_name,
            state=dialogue_state,
            audio_cache=audio_cache,
            frame_step_specs=frame_step_specs,
        )
        total_units = navigator.total_frames
        is_resuming = bool(dialogue_state.frames_completed)
        print(f"[TEACHER WS] Using FrameNavigator ({total_units} frames, lockstep)", flush=True)
    else:
        navigator = DagNavigator(
            lesson_plan=lesson_plan,
            animation_urls=animation_urls,
            teaching_style=teaching_style,
            student_name=student_name,
            state=dialogue_state,
        )
        total_units = navigator.total_segments
        is_resuming = bool(dialogue_state.segments_completed)
        print(f"[TEACHER WS] Using DagNavigator ({total_units} segments)", flush=True)

    # Send session info
    await websocket.send_json({
        "type": "session_info",
        "session_id": session_id,
        "lesson_title": lesson_plan.get("title", ""),
        "total_segments": total_units,
        "is_resuming": is_resuming,
    })

    # Start teaching in background task
    teaching_task = asyncio.create_task(_run_teaching(websocket, navigator, session_id))

    # Listen for incoming messages
    try:
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "speech_done":
                    navigator.acknowledge_speech()

                elif msg_type == "frame_done":
                    if hasattr(navigator, "acknowledge_frame_done"):
                        navigator.acknowledge_frame_done()

                elif msg_type == "response":
                    navigator.receive_response(msg.get("text", ""))

                elif msg_type == "raise_hand":
                    navigator.raise_hand(msg.get("student_name", student_name))

                elif msg_type == "lower_hand":
                    navigator.hand_raised = False

                elif msg_type == "question":
                    navigator.set_question(msg.get("text", ""))

                elif msg_type == "reaction":
                    dialogue_state.add_reaction(msg.get("reaction_type", ""))

                elif msg_type == "control":
                    action = msg.get("action", "")
                    if action == "pause":
                        navigator.paused = True
                    elif action == "resume":
                        navigator.paused = False
                    elif action == "leave":
                        break

            except json.JSONDecodeError:
                continue

    except WebSocketDisconnect:
        logger.info(f"Student disconnected from session {session_id}")
    finally:
        # Cancel teaching task
        teaching_task.cancel()
        try:
            await teaching_task
        except asyncio.CancelledError:
            pass

        # Save state and pause session.
        # NOTE: we keep the audio cache alive after pause so a quick reconnect
        # can resume instantly. Cache is only discarded on completion (in
        # session_manager.complete_session) or via the orphan cleanup hook.
        await session_manager.save_session_state(session_id, dialogue_state)
        await session_manager.pause_session(session_id)
        logger.info(f"Session {session_id} saved and paused")


async def _run_teaching(
    websocket: WebSocket,
    navigator,  # DagNavigator or FrameNavigator
    session_id: str,
) -> None:
    """Run the navigator and send messages to the client."""
    from app.services.tts import text_to_audio_base64

    msg_count = 0
    try:
        async for message in navigator.run():
            msg_count += 1
            msg_data = message.model_dump()

            # Log
            extra = ""
            if message.type == "speak":
                extra = f" text='{msg_data.get('text', '')[:60]}...'"
            elif message.type == "show_frame":
                extra = f" frame={msg_data.get('frame_id')} url={msg_data.get('frame_url', '')[:60]}"
            elif message.type == "frame_change":
                extra = f" frame={msg_data.get('frame_id')} {msg_data.get('frame_index')}/{msg_data.get('total_frames')}"
            elif message.type == "frame_bundle":
                steps_count = len(msg_data.get("steps", []))
                total_audio_kb = sum(
                    len(s.get("audio_b64", "")) for s in msg_data.get("steps", [])
                ) // 1024
                extra = f" frame={msg_data.get('frame_id')} {msg_data.get('frame_index')}/{msg_data.get('total_frames')} steps={steps_count} audio={total_audio_kb}KB"
            elif message.type == "animation_control":
                extra = f" action={msg_data.get('action')}"
            elif message.type == "wait":
                extra = f" {msg_data.get('seconds')}s ({msg_data.get('reason')})"
            print(f"[TEACH #{msg_count}] -> {message.type}{extra}", flush=True)

            if message.type == "speak":
                text = msg_data["text"]
                audio_b64 = msg_data.get("audio", "")

                # If audio was pre-generated by FrameNavigator, use it directly
                if not audio_b64:
                    # Generate on-the-fly (opening, closing, etc.)
                    try:
                        audio_b64 = await text_to_audio_base64(text)
                    except Exception as e:
                        print(f"[TEACH #{msg_count}] TTS failed: {e}", flush=True)

                if audio_b64:
                    await websocket.send_json({
                        "type": "speak_audio",
                        "audio": audio_b64,
                        "text": text,
                        "speech_type": msg_data.get("speech_type", "teaching"),
                    })
                    print(f"[TEACH #{msg_count}] speak_audio sent ({len(audio_b64) // 1024}KB)", flush=True)
                else:
                    await websocket.send_json(msg_data)
                    print(f"[TEACH #{msg_count}] text-only fallback", flush=True)

                # Wait for frontend to finish playing audio
                navigator._speech_done_event.clear()
                print(f"[TEACH #{msg_count}] Waiting for speech_done...", flush=True)
                try:
                    await asyncio.wait_for(
                        navigator._speech_done_event.wait(), timeout=180,
                    )
                    print(f"[TEACH #{msg_count}] speech_done received", flush=True)
                except asyncio.TimeoutError:
                    print(f"[TEACH #{msg_count}] speech_done TIMEOUT — continuing", flush=True)
            else:
                # Non-speak messages: send directly
                await websocket.send_json(msg_data)

            # If it's a wait message, actually pause
            if message.type == "wait":
                await asyncio.sleep(message.seconds)

            # Periodically save state (every segment/frame change/bundle)
            if message.type in ("segment_change", "frame_change", "frame_bundle"):
                await session_manager.save_session_state(
                    session_id, navigator.state,
                )

            # If session complete, save summary
            if message.type == "session_complete":
                await session_manager.complete_session(
                    session_id, message.summary,
                )

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Teaching error in session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Teaching error: {str(e)[:200]}",
                "recoverable": True,
            })
        except Exception:
            pass
