"""
Course Planner v4 — Progressive visual-first storyboard generator.

Progressive pipeline (student starts learning while later lessons generate):
1. Structure: modules + lesson outlines (~1 min)
2. First batch: generate lessons 1-2 storyboards (~5 min)
3. Save + mark ready — STUDENT CAN START LESSON 1
4. Background: generate remaining lessons in batches of 3
5. Each batch saved incrementally — lessons become available as they complete

Continuity: Course structure (step 1) defines the full outline with
prerequisites. Each lesson storyboard is generated with knowledge of
what came before, so later lessons build on earlier ones naturally.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.engine.claude_engine import ClaudeEngine
from app.agents.course_planner.prompts_v4 import (
    STRUCTURE_V4_SYSTEM,
    STRUCTURE_V4_PROMPT,
    LESSON_STORYBOARD_SYSTEM,
    LESSON_STORYBOARD_PROMPT,
    STORYBOARD_REVIEW_SYSTEM,
    STORYBOARD_REVIEW_PROMPT,
)
from app.services.agent_task import fetch_onboarding_data, fetch_research_results, fetch_research_sources
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


def _build_research_context(research_results: dict, research_sources: list) -> dict:
    """Build context from research data for the course planner."""
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

    formulas, code_snippets, key_concepts, visual_opps, misconceptions, analogies = [], [], [], [], [], []

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
            for m in ec.get("misconceptions", []):
                misconceptions.append((m if isinstance(m, str) else m.get("misconception", ""))[:60])
            for a in ec.get("analogies", []):
                analogies.append((a if isinstance(a, str) else a.get("analogy", ""))[:60])

    return {
        "key_concepts": ", ".join(list(set(key_concepts))[:15]) or "None found",
        "visual_opportunities": "\n".join(visual_opps[:8]) or "None specified",
    }


async def run_course_planner_v4(goal_id: str, user_id: str) -> dict:
    """Run progressive course planner — first lessons ready in ~5 min."""
    sb = get_supabase()
    engine = ClaudeEngine(model="opus")

    def progress(msg: str, pct: int | None = None):
        update = {"current_task": msg}
        if pct is not None:
            update["progress_percentage"] = pct
        try:
            sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
        except Exception:
            pass
        logger.info(f"[CoursePlanner v4] {msg}")

    try:
        sb.table("agent_tasks").update({
            "status": "active", "progress_percentage": 2,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
    except Exception:
        pass

    # ── Load data ──
    progress("Loading research data + student profile...", 5)

    onboarding = await fetch_onboarding_data(goal_id, user_id)
    research_results = await fetch_research_results(goal_id)
    research_sources = await fetch_research_sources(goal_id)

    if not research_results:
        _fail(sb, goal_id, "Research not completed")
        raise RuntimeError("Research not completed")

    goal = onboarding.get("goal", {})
    prefs = onboarding.get("preferences", {})
    profile = onboarding.get("profile", {})
    research_ctx = _build_research_context(research_results, research_sources)

    student_name = ""
    try:
        prof = sb.table("profiles").select("name, email").eq("id", user_id).single().execute()
        if prof.data:
            student_name = prof.data.get("name") or prof.data.get("email", "").split("@")[0] or "Student"
    except Exception:
        student_name = "Student"

    # ── STEP 1: Course Structure (~1 min) ──
    progress("Designing course structure...", 10)
    session_duration = prefs.get("session_duration_minutes", 30)

    structure_prompt = STRUCTURE_V4_PROMPT.format(
        goal_title=goal.get("title", "Unknown"),
        end_goal=goal.get("end_goal", "Not specified"),
        education_level=profile.get("education_level", "self_learner"),
        content_depth=prefs.get("content_depth", "intermediate"),
        session_duration_minutes=session_duration,
        topics_summary=research_ctx["topics_summary"],
    )

    try:
        struct_result = await engine.run(
            prompt=structure_prompt,
            system_prompt=STRUCTURE_V4_SYSTEM,
            timeout=300,
        )
        course_structure = json.loads(struct_result["result"])
    except Exception as e:
        _fail(sb, goal_id, f"Structure generation failed: {e}")
        raise

    all_lessons = []
    for module in course_structure.get("modules", []):
        for lesson in module.get("lessons", []):
            all_lessons.append(lesson)

    progress(f"Structure ready: {len(course_structure.get('modules', []))} modules, {len(all_lessons)} lessons", 15)

    # ── Shared storyboard generator ──
    async def generate_storyboard(lesson: dict) -> dict:
        """Generate + review storyboard for one lesson."""
        lesson_id = lesson.get("lesson_id", "")
        lesson_topics = lesson.get("topics_covered", [])
        lesson_research = _build_lesson_research(lesson_topics, research_sources, research_ctx["synthesis"])

        prompt = LESSON_STORYBOARD_PROMPT.format(
            lesson_title=lesson.get("title", ""),
            lesson_type=lesson.get("lesson_type", "theory"),
            estimated_minutes=lesson.get("estimated_minutes", 30),
            objectives=", ".join(lesson.get("learning_objectives", [])),
            topics=", ".join(lesson_topics),
            education_level=profile.get("education_level", "self_learner"),
            learning_style=prefs.get("learning_style", "visual"),
            student_name=student_name,
            key_concepts=lesson_research["key_concepts"],
            visual_opportunities=lesson_research["visual_opportunities"],
        )

        progress(f"[{lesson_id}] Generating: {lesson.get('title', '')[:40]}...")

        try:
            # Pass 1: Generate
            result = await engine.run(
                prompt=prompt,
                system_prompt=LESSON_STORYBOARD_SYSTEM,
                timeout=600,
            )
            storyboard = json.loads(result["result"])
            frames = storyboard.get("frames", [])
            progress(f"[{lesson_id}] Pass 1: {len(frames)} frames. Reviewing...")

            # Pass 2: Self-review
            review_notes = []
            try:
                review_prompt = STORYBOARD_REVIEW_PROMPT.format(
                    lesson_title=lesson.get("title", ""),
                    student_name=student_name,
                    education_level=profile.get("education_level", "self_learner"),
                    storyboard_json=json.dumps(storyboard, indent=2)[:8000],
                )
                review_result = await engine.run(
                    prompt=review_prompt,
                    system_prompt=STORYBOARD_REVIEW_SYSTEM,
                    timeout=600,
                )
                reviewed = json.loads(review_result["result"])
                reviewed_frames = reviewed.get("frames", [])
                review_notes = reviewed.get("review_notes", [])
                if reviewed_frames:
                    frames = reviewed_frames
                    progress(f"[{lesson_id}] Review: {len(review_notes)} fixes")
            except Exception as re:
                logger.warning(f"[CoursePlanner v4] Review skipped for {lesson_id}: {re}")

            return {
                "lesson_id": lesson_id,
                "title": lesson.get("title", ""),
                "opening_hook": storyboard.get("opening_hook", ""),
                "closing_summary": storyboard.get("closing_summary", []),
                "frames": frames,
                "total_frames": len(frames),
                "total_interactions": sum(1 for f in frames if f.get("interaction")),
                "review_notes": review_notes,
            }
        except Exception as e:
            logger.error(f"[CoursePlanner v4] {lesson_id} failed: {e}")
            return {"lesson_id": lesson_id, "title": lesson.get("title", ""), "frames": [], "error": str(e)}

    # ── Shared save function ──
    def save_to_db(lesson_plans: dict, is_final: bool = False):
        """Save current state to DB incrementally."""
        total_frames = sum(lp.get("total_frames", 0) for lp in lesson_plans.values())
        total_interactions = sum(lp.get("total_interactions", 0) for lp in lesson_plans.values())
        ready_count = sum(1 for lp in lesson_plans.values() if lp.get("frames"))

        try:
            sb.table("course_plans").upsert({
                "goal_id": goal_id,
                "user_id": user_id,
                "course_structure": course_structure,
                "lesson_plans": lesson_plans,
                "student_resource_map": {},
                "generation_metadata": {
                    "version": 4,
                    "engine": "claude_code",
                    "progressive": True,
                    "total_frames": total_frames,
                    "total_interactions": total_interactions,
                    "lessons_ready": ready_count,
                    "lessons_total": len(all_lessons),
                    "is_complete": is_final,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                "total_lessons": len(all_lessons),
                "total_modules": len(course_structure.get("modules", [])),
                "total_estimated_minutes": course_structure.get("total_estimated_minutes", 0),
                "version": 4,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="goal_id").execute()
        except Exception as e:
            logger.error(f"[CoursePlanner v4] DB save failed: {e}")

        return total_frames, total_interactions, ready_count

    # ── STEP 2: First batch — lessons 1-2 (~5 min) ──
    first_batch_size = min(2, len(all_lessons))
    first_batch = all_lessons[:first_batch_size]
    remaining = all_lessons[first_batch_size:]

    progress(f"Generating first {first_batch_size} lessons (student can start soon)...", 20)

    first_results = await asyncio.gather(
        *[generate_storyboard(l) for l in first_batch],
        return_exceptions=True,
    )

    lesson_plans = {}
    for r in first_results:
        if isinstance(r, dict) and r.get("lesson_id"):
            lesson_plans[r["lesson_id"]] = r

    # Save first batch — student can start!
    tf, ti, ready = save_to_db(lesson_plans)
    progress(f"First {ready} lessons ready! Student can start. {tf} frames, {ti} interactions.", 40)

    # ── STEP 3: Remaining lessons in background batches ──
    if remaining:
        batch_size = 3
        for i in range(0, len(remaining), batch_size):
            batch = remaining[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_remaining_batches = (len(remaining) + batch_size - 1) // batch_size

            pct = 40 + int(50 * (i + batch_size) / len(remaining))
            progress(f"Background batch {batch_num}/{total_remaining_batches}: generating {len(batch)} lessons...", min(pct, 90))

            batch_results = await asyncio.gather(
                *[generate_storyboard(l) for l in batch],
                return_exceptions=True,
            )

            for r in batch_results:
                if isinstance(r, dict) and r.get("lesson_id"):
                    lesson_plans[r["lesson_id"]] = r

            # Save incrementally after each batch
            tf, ti, ready = save_to_db(lesson_plans)
            progress(f"{ready}/{len(all_lessons)} lessons ready. {tf} frames total.", min(pct, 92))

    # ── Final save ──
    tf, ti, ready = save_to_db(lesson_plans, is_final=True)

    progress(f"Course complete! {ready}/{len(all_lessons)} lessons, {tf} frames, {ti} interactions", 100)
    sb.table("agent_tasks").update({
        "status": "completed",
        "progress_percentage": 100,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()

    logger.info(
        f"[CoursePlanner v4] DONE: {len(course_structure.get('modules', []))} modules, "
        f"{ready} lessons, {tf} frames, {ti} interactions"
    )

    return {"course_structure": course_structure, "lesson_plans": lesson_plans,
            "generation_metadata": {"total_frames": tf, "total_interactions": ti}}


def _fail(sb, goal_id, msg):
    sb.table("agent_tasks").update({
        "status": "failed", "error_message": msg, "progress_percentage": 0,
    }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
