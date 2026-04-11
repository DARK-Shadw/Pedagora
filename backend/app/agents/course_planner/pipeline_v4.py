"""
Course Planner v4 — Sequential per-lesson storyboard generator with live streaming.

Pipeline (orchestrator-driven):
  research → structure → for each lesson: storyboard(L) → animation(L)

This module exposes two low-level functions used by pipeline_orchestrator:
  - generate_course_structure_v4  (Stage 1: modules + lesson outlines)
  - generate_one_lesson_storyboard_v4  (Stage 2: one lesson, streamed)

It also keeps run_course_planner_v4 as a backwards-compat entry point used by
the /agents/course-plan retry endpoint (planning only, no animation).
"""

import asyncio
import json
import logging
import re
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.engine.claude_engine import ClaudeEngine
from app.agents.course_planner.prompts_v4 import (
    STRUCTURE_V4_SYSTEM,
    STRUCTURE_V4_PROMPT,
    LESSON_STORYBOARD_SYSTEM,
    LESSON_STORYBOARD_PROMPT,
)
from app.agents.critic.orchestrator import CriticReport, review_lesson
from app.services.agent_task import fetch_onboarding_data, fetch_research_results, fetch_research_sources
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

CRITIC_LOG_DIR = Path(__file__).resolve().parents[3] / "logs" / "planner_critic"
MAX_REGEN_ATTEMPTS = 2  # one initial gen + up to 2 retries

# Regex to detect new frames appearing in a streaming JSON blob.
_FRAME_ID_RE = re.compile(r'"frame_id"\s*:\s*"([^"]+)"')


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────

def _strip_md_fences(text: str) -> str:
    """Remove leading ```json / ``` fences that Claude sometimes wraps output in."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first line (the fence opener) and last line if it's a fence closer
        start = 1
        end = len(lines)
        if lines[-1].strip() in ("```", "```json"):
            end -= 1
        text = "\n".join(lines[start:end]).strip()
    return text


def _flatten_lessons(course_structure: dict) -> list[dict]:
    """Collect all lesson dicts from all modules in order."""
    lessons = []
    for module in course_structure.get("modules", []):
        for lesson in module.get("lessons", []):
            lessons.append(lesson)
    return lessons


def _build_research_context(research_results: dict, research_sources: list) -> dict:
    """Summarise research for the structure stage."""
    topic_tree = research_results.get("topic_tree", {})
    synthesis = research_results.get("synthesis", {})
    topics = topic_tree.get("topic_groups", [])

    topics_summary = "\n".join(
        f"- [{t.get('priority', '?')}] {t.get('topic_name', '?')}"
        for t in topics
    )

    teaching_notes = ""
    notes = synthesis.get("teaching_notes", {})
    if isinstance(notes, dict):
        teaching_notes = "\n".join(f"- {k}: {v}" for k, v in list(notes.items())[:10])

    return {
        "topics_summary": topics_summary or "No topics found",
        "teaching_notes": teaching_notes or "None",
        "topics": topics,
        "sources": research_sources,
        "synthesis": synthesis,
    }


def _build_lesson_research(lesson_topics: list[str], sources: list, synthesis: dict) -> dict:
    """Filter research data relevant to a specific lesson."""
    relevant = [s for s in sources if s.get("topic_group", "") in lesson_topics]
    if not relevant:
        relevant = sources[:5]

    formulas, code_snippets, key_concepts, visual_opps = [], [], [], []

    for s in relevant:
        key_concepts.extend(s.get("key_concepts", [])[:3])
        for f in (s.get("formulas") or []):
            if isinstance(f, dict):
                formulas.append(f"{f.get('formula_latex', '?')} — {f.get('context', '')[:60]}")
        for c in (s.get("code_snippets") or []):
            if isinstance(c, dict):
                code_snippets.append(f"{c.get('description', '?')[:60]}")
        ec = s.get("extracted_content", {})
        if isinstance(ec, dict):
            vo = ec.get("visual_opportunity", "")
            if vo:
                visual_opps.append(vo[:80])

    return {
        "key_concepts": ", ".join(list(set(key_concepts))[:15]) or "None found",
        "visual_opportunities": "\n".join(visual_opps[:8]) or "None specified",
    }


def _make_progress(sb, goal_id: str):
    """Return (milestone, ticker) callables for a planning task.

    milestone(msg, pct=None) — updates current_task + optional pct + appends
        a log entry via the append_agent_task_log RPC. Use for meaningful
        events: structure ready, frame detected, critic PASS/FAIL, etc.

    ticker(msg) — bare UPDATE of current_task only. No RPC, no log entry.
        Use inside _stream_with_progress to show live streaming status in the
        CURRENT TASK column without flooding System Execution Logs.
    """

    def milestone(msg: str, pct: int | None = None):
        update: dict = {"current_task": msg}
        if pct is not None:
            update["progress_percentage"] = pct
        try:
            sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
        except Exception:
            pass
        try:
            sb.rpc(
                "append_agent_task_log",
                {
                    "p_goal_id": goal_id,
                    "p_agent_type": "planning",
                    "p_log_entry": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "agent": "planning",
                        "message": msg,
                        "level": "info",
                    },
                },
            ).execute()
        except Exception:
            pass
        logger.info(f"[CoursePlanner v4] {msg}")

    def ticker(msg: str):
        """Update current_task only — no RPC, no log append."""
        try:
            sb.table("agent_tasks").update({"current_task": msg}).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
        except Exception:
            pass

    return milestone, ticker


async def _stream_with_progress(
    engine: ClaudeEngine,
    prompt: str,
    system_prompt: str,
    milestone: Callable,
    ticker: Callable,
    label: str,
    timeout: int = 1500,
) -> str:
    """Stream a Claude generation and surface real-time progress.

    - Logs a milestone each time a new "frame_id" appears in the partial JSON.
    - Calls ticker (no log) every 3 s with the current character + frame count
      so the CURRENT TASK column stays alive during long silences.
    - Returns the final text (from result event or buffer fallback).
    """
    buffer: list[str] = []
    seen_frames: set[str] = set()
    last_tick = _time.monotonic()
    last_buf_len = 0
    final_result: str | None = None
    stream_started = False  # True once first text event arrives

    # Background heartbeat — ticks the UI every 10 s even during the thinking
    # phase when engine.stream() yields nothing (Opus can think for 5-10 min
    # before writing a single character, so the event loop never enters the
    # text branch below and the ticker never fires without this task).
    async def _heartbeat():
        start = _time.monotonic()
        while True:
            await asyncio.sleep(10)
            elapsed = int(_time.monotonic() - start)
            if not stream_started:
                ticker(f"{label} … model thinking ({elapsed}s)")
            else:
                buf_len = sum(len(c) for c in buffer)
                n = len(seen_frames)
                ticker(
                    f"{label} … {buf_len:,} chars — "
                    f"{n} frame{'s' if n != 1 else ''} found"
                )

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        async for event in engine.stream(
            prompt=prompt,
            system_prompt=system_prompt,
            timeout=timeout,
        ):
            etype = event.get("type")

            if etype == "text":
                if not stream_started:
                    stream_started = True
                    ticker(f"{label} … streaming started")

                chunk = event.get("content", "")
                buffer.append(chunk)
                full = "".join(buffer)

                # Emit a milestone for each new frame_id found in the partial JSON
                for m in _FRAME_ID_RE.finditer(full):
                    fid = m.group(1)
                    if fid not in seen_frames:
                        seen_frames.add(fid)
                        milestone(f"{label} ✓ frame {len(seen_frames)}: {fid}")

                # Ticker: max once per 3 s, only if buffer actually grew
                now = _time.monotonic()
                if now - last_tick >= 3 and len(full) > last_buf_len:
                    ticker(
                        f"{label} … {len(full):,} chars — "
                        f"{len(seen_frames)} frame{'s' if len(seen_frames) != 1 else ''} found"
                    )
                    last_tick = now
                    last_buf_len = len(full)

            elif etype == "result":
                final_result = event.get("result") or None

            elif etype == "error":
                raise RuntimeError(f"[stream error] {event.get('message', 'unknown')}")

    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    return final_result if final_result is not None else "".join(buffer)


def _save_lesson_plan_to_db(sb, goal_id: str, lesson_id: str, lesson_plan: dict) -> None:
    """Atomically merge one lesson_plan into course_plans.lesson_plans[lesson_id]."""
    try:
        row = sb.table("course_plans").select("lesson_plans, generation_metadata").eq("goal_id", goal_id).single().execute()
        existing_plans: dict = (row.data or {}).get("lesson_plans") or {}
        existing_meta: dict = (row.data or {}).get("generation_metadata") or {}

        existing_plans[lesson_id] = lesson_plan

        # Recompute summary fields
        total_frames = sum(lp.get("total_frames", 0) for lp in existing_plans.values() if isinstance(lp, dict))
        lessons_ready = sum(1 for lp in existing_plans.values() if isinstance(lp, dict) and lp.get("frames"))

        new_meta = {
            **existing_meta,
            "total_frames": total_frames,
            "lessons_ready": lessons_ready,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        sb.table("course_plans").update({
            "lesson_plans": existing_plans,
            "generation_metadata": new_meta,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("goal_id", goal_id).execute()

    except Exception as e:
        logger.error(f"[CoursePlanner v4] _save_lesson_plan_to_db failed for {lesson_id}: {e}")


def _fail(sb, goal_id: str, msg: str) -> None:
    try:
        sb.table("agent_tasks").update({
            "status": "failed",
            "error_message": msg,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
    except Exception:
        pass
    try:
        sb.rpc(
            "append_agent_task_log",
            {
                "p_goal_id": goal_id,
                "p_agent_type": "planning",
                "p_log_entry": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent": "planning",
                    "message": f"FAILED: {msg}",
                    "level": "error",
                },
            },
        ).execute()
    except Exception:
        pass


def _log_critic_report(lesson_id: str, attempt: int, report: CriticReport) -> None:
    """Persist a per-attempt critic report under logs/planner_critic/."""
    try:
        CRITIC_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = CRITIC_LOG_DIR / f"{lesson_id}_attempt{attempt}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[CoursePlanner v4] failed to log critic report: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — Course Structure
# ──────────────────────────────────────────────────────────────────────────────

async def generate_course_structure_v4(goal_id: str, user_id: str) -> dict:
    """Stage 1: load context + generate course structure (~1 min).

    Saves a stub course_plans row with empty lesson_plans so that per-lesson
    upserts in Stage 2 can safely merge into the JSONB column.

    Returns:
        {
          "course_structure": {...},
          "all_lessons": [...],    # flat list across all modules
          "context": {             # passed through to generate_one_lesson_storyboard_v4
            "goal", "prefs", "profile", "student_name",
            "research_ctx", "research_sources"
          }
        }
    """
    sb = get_supabase()
    engine = ClaudeEngine(model="opus")
    milestone, ticker = _make_progress(sb, goal_id)

    milestone("Loading research data + student profile...", 5)

    onboarding = await fetch_onboarding_data(goal_id, user_id)
    research_results = await fetch_research_results(goal_id)
    research_sources = await fetch_research_sources(goal_id)

    if not research_results:
        _fail(sb, goal_id, "Research not completed — cannot plan course")
        raise RuntimeError("Research not completed")

    goal = onboarding.get("goal") or {}
    prefs = onboarding.get("preferences") or {}
    profile = onboarding.get("profile") or {}
    research_ctx = _build_research_context(research_results, research_sources)

    student_name = "Student"
    try:
        prof = sb.table("profiles").select("name, email").eq("id", user_id).single().execute()
        if prof.data:
            student_name = (
                prof.data.get("name")
                or (prof.data.get("email") or "").split("@")[0]
                or "Student"
            )
    except Exception:
        pass

    milestone("Designing course structure...", 10)

    structure_prompt = STRUCTURE_V4_PROMPT.format(
        goal_title=goal.get("title", "Unknown"),
        end_goal=goal.get("end_goal", "Not specified"),
        education_level=profile.get("education_level", "self_learner"),
        content_depth=prefs.get("content_depth", "intermediate"),
        session_duration_minutes=prefs.get("session_duration_minutes", 30),
        topics_summary=research_ctx["topics_summary"],
    )

    try:
        struct_result = await engine.run(
            prompt=structure_prompt,
            system_prompt=STRUCTURE_V4_SYSTEM,
            timeout=600,
        )
        raw = struct_result.get("result", "")
        course_structure = json.loads(_strip_md_fences(raw))
    except Exception as e:
        _fail(sb, goal_id, f"Structure generation failed: {e}")
        raise

    all_lessons = _flatten_lessons(course_structure)

    # Save stub so per-lesson upserts can merge safely
    try:
        sb.table("course_plans").upsert({
            "goal_id": goal_id,
            "user_id": user_id,
            "course_structure": course_structure,
            "lesson_plans": {},
            "student_resource_map": {},
            "generation_metadata": {
                "version": 4,
                "engine": "claude_code",
                "progressive": True,
                "is_complete": False,
                "lessons_total": len(all_lessons),
                "lessons_ready": 0,
                "total_frames": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            "total_lessons": len(all_lessons),
            "total_modules": len(course_structure.get("modules", [])),
            "total_estimated_minutes": course_structure.get("total_estimated_minutes", 0),
            "version": 4,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="goal_id").execute()
    except Exception as e:
        logger.error(f"[CoursePlanner v4] stub DB save failed: {e}")

    milestone(
        f"Structure ready: {len(course_structure.get('modules', []))} modules, "
        f"{len(all_lessons)} lessons",
        15,
    )

    return {
        "course_structure": course_structure,
        "all_lessons": all_lessons,
        "context": {
            "goal": goal,
            "prefs": prefs,
            "profile": profile,
            "student_name": student_name,
            "research_ctx": research_ctx,
            "research_sources": research_sources,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Per-lesson storyboard (streaming + critic gate)
# ──────────────────────────────────────────────────────────────────────────────

async def generate_one_lesson_storyboard_v4(
    goal_id: str,
    user_id: str,
    lesson: dict,
    context: dict,
    overall_pct: int | None = None,
) -> dict:
    """Stage 2 (one lesson): stream → critic gate → incremental DB save.

    Args:
        lesson:      A lesson dict from the structure stage (has lesson_id, title, …).
        context:     The "context" sub-dict returned by generate_course_structure_v4.
        overall_pct: Optional progress percentage to write alongside the milestone.

    Returns:
        lesson_plan dict (has lesson_id, frames, critic info, or error key on failure).
    """
    sb = get_supabase()
    engine = ClaudeEngine(model="opus")
    milestone, ticker = _make_progress(sb, goal_id)

    goal = context["goal"]
    prefs = context["prefs"]
    profile = context["profile"]
    student_name = context["student_name"]
    research_ctx = context["research_ctx"]
    research_sources = context["research_sources"]

    lesson_id = lesson.get("lesson_id", "")
    lesson_topics = lesson.get("topics_covered", [])
    lesson_research = _build_lesson_research(lesson_topics, research_sources, research_ctx.get("synthesis", {}))

    base_prompt = LESSON_STORYBOARD_PROMPT.format(
        lesson_title=lesson.get("title", ""),
        lesson_type=lesson.get("lesson_type", "theory"),
        estimated_minutes=lesson.get("estimated_minutes", 30),
        objectives=", ".join(lesson.get("learning_objectives", [])),
        topics=", ".join(lesson_topics),
        education_level=profile.get("education_level", "self_learner"),
        learning_style=prefs.get("learning_style", "visual"),
        student_name=student_name,
        end_goal=goal.get("end_goal", "Not specified"),
        key_concepts=lesson_research["key_concepts"],
        visual_opportunities=lesson_research["visual_opportunities"],
    )

    milestone(f"[{lesson_id}] Generating: {lesson.get('title', '')[:40]}...", overall_pct)

    attempt = 0
    last_storyboard: dict | None = None
    last_critic: CriticReport | None = None

    while attempt <= MAX_REGEN_ATTEMPTS:
        attempt += 1
        label = f"[{lesson_id}] attempt {attempt}"

        try:
            if attempt == 1 or last_critic is None:
                prompt = base_prompt
            else:
                feedback = last_critic.feedback_for_regeneration()
                prompt = (
                    base_prompt
                    + "\n\n=== PRIOR ATTEMPT FAILED — CRITIC FEEDBACK ===\n"
                    + feedback
                    + "\n\nFix every blocking issue above and emit a new storyboard."
                )

            raw = await _stream_with_progress(
                engine=engine,
                prompt=prompt,
                system_prompt=LESSON_STORYBOARD_SYSTEM,
                milestone=milestone,
                ticker=ticker,
                label=label,
                timeout=1500,
            )

            cleaned = _strip_md_fences(raw)
            try:
                storyboard = json.loads(cleaned)
            except json.JSONDecodeError:
                # Try to extract the largest JSON object from the text
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start >= 0 and end > start:
                    storyboard = json.loads(cleaned[start:end + 1])
                else:
                    raise

            last_storyboard = storyboard
            frames = storyboard.get("frames", [])
            milestone(f"[{lesson_id}] Attempt {attempt}: {len(frames)} frames — running critic...")

            lesson_dict_for_critic = {
                "lesson_id": lesson_id,
                "title": lesson.get("title", ""),
                "frames": frames,
            }
            report = await review_lesson(
                lesson=lesson_dict_for_critic,
                lesson_title=lesson.get("title", ""),
                end_goal=goal.get("end_goal", ""),
                skip_narrative=(attempt < MAX_REGEN_ATTEMPTS + 1),
            )
            last_critic = report
            _log_critic_report(lesson_id, attempt, report)

            if report.passed:
                milestone(f"[{lesson_id}] Critic PASS (attempt {attempt})")
                break

            milestone(
                f"[{lesson_id}] Critic FAIL (attempt {attempt}): "
                f"{len(report.blocking)} blocking — regenerating..."
            )

        except Exception as e:
            logger.error(f"[CoursePlanner v4] {lesson_id} attempt {attempt} error: {e}")
            if attempt > MAX_REGEN_ATTEMPTS:
                lesson_plan = {
                    "lesson_id": lesson_id,
                    "title": lesson.get("title", ""),
                    "frames": [],
                    "error": str(e),
                }
                _save_lesson_plan_to_db(sb, goal_id, lesson_id, lesson_plan)
                return lesson_plan
            # else: loop continues to the next attempt

    if last_storyboard is None:
        lesson_plan = {
            "lesson_id": lesson_id,
            "title": lesson.get("title", ""),
            "frames": [],
            "error": "no attempts completed",
        }
        _save_lesson_plan_to_db(sb, goal_id, lesson_id, lesson_plan)
        return lesson_plan

    frames = last_storyboard.get("frames", [])
    critic_dict = last_critic.to_dict() if last_critic else None
    lesson_plan = {
        "lesson_id": lesson_id,
        "title": lesson.get("title", ""),
        "opening_hook": last_storyboard.get("opening_hook", ""),
        "closing_summary": last_storyboard.get("closing_summary", []),
        "frames": frames,
        "total_frames": len(frames),
        "total_interactions": sum(1 for f in frames if f.get("interaction")),
        "critic": critic_dict,
        "critic_passed": (last_critic.passed if last_critic else False),
    }
    _save_lesson_plan_to_db(sb, goal_id, lesson_id, lesson_plan)
    milestone(f"[{lesson_id}] Saved — {len(frames)} frames")
    return lesson_plan


# ──────────────────────────────────────────────────────────────────────────────
# Backwards-compat entry point (used by /agents/course-plan retry endpoint)
# ──────────────────────────────────────────────────────────────────────────────

async def run_course_planner_v4(goal_id: str, user_id: str) -> dict:
    """Planning-only sequential runner. Used by the retry endpoint.

    Does NOT run animations — that is the pipeline_orchestrator's job.
    Marks the planning task as active/completed/failed directly since the
    orchestrator is NOT managing started_at/completed_at for this path.
    """
    sb = get_supabase()
    milestone, _ = _make_progress(sb, goal_id)

    # Mark active now (orchestrator doesn't run on this path)
    try:
        sb.table("agent_tasks").update({
            "status": "active",
            "progress_percentage": 2,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
    except Exception:
        pass

    try:
        struct = await generate_course_structure_v4(goal_id, user_id)
    except Exception as e:
        logger.exception(f"[CoursePlanner v4] structure stage crashed: {e}")
        _fail(sb, goal_id, f"Structure stage failed: {type(e).__name__}: {str(e)[:200]}")
        raise

    all_lessons = struct["all_lessons"]
    context = struct["context"]
    total = len(all_lessons)
    lesson_plans: dict[str, dict] = {}

    for i, lesson in enumerate(all_lessons):
        pct = 15 + int(80 * (i + 1) / max(total, 1))
        lesson_id = lesson.get("lesson_id", f"lesson-{i}")
        try:
            lp = await generate_one_lesson_storyboard_v4(
                goal_id=goal_id,
                user_id=user_id,
                lesson=lesson,
                context=context,
                overall_pct=pct,
            )
            if lp.get("lesson_id"):
                lesson_plans[lp["lesson_id"]] = lp
        except Exception as e:
            logger.error(f"[CoursePlanner v4] lesson {lesson_id} crashed (skipping): {e}")
            continue

    done = sum(1 for lp in lesson_plans.values() if lp.get("frames") and not lp.get("error"))
    milestone(f"Planning complete — {done}/{total} lessons ready", 100)

    try:
        sb.table("agent_tasks").update({
            "status": "completed",
            "progress_percentage": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
    except Exception:
        pass

    # Mark generation as complete in course_plans metadata
    try:
        row = sb.table("course_plans").select("generation_metadata").eq("goal_id", goal_id).single().execute()
        meta = (row.data or {}).get("generation_metadata") or {}
        sb.table("course_plans").update({
            "generation_metadata": {
                **meta,
                "is_complete": True,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("goal_id", goal_id).execute()
    except Exception:
        pass

    return {
        "course_structure": struct["course_structure"],
        "lesson_plans": lesson_plans,
    }
