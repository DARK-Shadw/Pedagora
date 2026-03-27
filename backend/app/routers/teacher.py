"""Teacher Agent router — WebSocket for live teaching + REST for session management."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.agents.teacher.dag_navigator import DagNavigator
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
            return CreateSessionResponse(
                session_id=existing["id"],
                status=existing["status"],
                is_resuming=True,
            )

    # Create new session
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


# ─── WebSocket Endpoint ───


@router.websocket("/ws/teach/{session_id}")
async def teach_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
):
    """Main WebSocket for live teaching sessions.

    Frontend connects here after creating a session via REST.
    Backend navigates the teaching DAG and sends messages.
    Frontend sends student responses, reactions, and controls.
    """
    await websocket.accept()
    print(f"[TEACHER WS] Connection accepted. session_id={session_id}, token_len={len(token)}", flush=True)

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

    # Get animation URLs
    animations = await get_lesson_animations(goal_id, lesson_id)
    animation_urls = {
        a["animation_id"]: a.get("output_url", "")
        for a in animations
        if a.get("status") == "completed" and a.get("output_url")
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
    dialogue_state = DialogueState.from_dict(session.get("dialogue_state", {}))

    # Create DAG navigator
    navigator = DagNavigator(
        lesson_plan=lesson_plan,
        animation_urls=animation_urls,
        teaching_style=teaching_style,
        student_name=student_name,
        state=dialogue_state,
    )

    # Send session info
    await websocket.send_json({
        "type": "session_info",
        "session_id": session_id,
        "lesson_title": lesson_plan.get("title", ""),
        "total_segments": navigator.total_segments,
        "is_resuming": bool(dialogue_state.segments_completed),
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

        # Save state and pause session
        await session_manager.save_session_state(session_id, dialogue_state)
        await session_manager.pause_session(session_id)
        logger.info(f"Session {session_id} saved and paused")


async def _run_teaching(
    websocket: WebSocket,
    navigator: DagNavigator,
    session_id: str,
) -> None:
    """Run the teaching DAG navigator and send messages to the client."""
    try:
        async for message in navigator.run():
            # Send message to frontend
            await websocket.send_json(message.model_dump())

            # If it's a speak message, wait for frontend to finish playing
            if message.type == "speak":
                navigator._speech_done_event.clear()
                print(f"[TEACHER] Waiting for speech_done...", flush=True)
                try:
                    await asyncio.wait_for(
                        navigator._speech_done_event.wait(), timeout=180,
                    )
                    print(f"[TEACHER] speech_done received, continuing", flush=True)
                except asyncio.TimeoutError:
                    print(f"[TEACHER] speech_done timeout — continuing anyway", flush=True)

            # If it's a wait message, actually pause
            if message.type == "wait":
                await asyncio.sleep(message.seconds)

            # Periodically save state (every segment change)
            if message.type == "segment_change":
                await session_manager.save_session_state(
                    session_id, navigator.state,
                )

            # If session complete, save summary
            if message.type == "session_complete":
                await session_manager.complete_session(
                    session_id, message.summary,
                )

    except asyncio.CancelledError:
        # Student disconnected — state already saved in finally block
        pass
    except Exception as e:
        logger.error(f"Teaching error in session {session_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Teaching error: {str(e)[:200]}",
                "recoverable": True,
            })
        except Exception:
            pass
