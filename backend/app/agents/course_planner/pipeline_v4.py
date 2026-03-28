"""
Course Planner v4 — Visual-first storyboard generator via Claude Code.

Three-stage pipeline:
1. Structure: modules + lesson outlines (~1 min)
2. Storyboard: parallel frame-by-frame visual scripts per lesson (~3-5 min)
3. Review: self-review pass fixes pacing, sequencing, interaction quality (~2 min)

Output: course_plans table with VisualFrame[] storyboards per lesson.
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
    # Find sources matching lesson topics
    relevant = [s for s in sources if s.get("topic_group", "") in lesson_topics]
    if not relevant:
        relevant = sources[:5]  # Fallback: use first 5 sources

    formulas = []
    code_snippets = []
    key_concepts = []
    visual_opps = []
    misconceptions = []
    analogies = []

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
                if isinstance(m, str):
                    misconceptions.append(m[:60])
                elif isinstance(m, dict):
                    misconceptions.append(m.get("misconception", "")[:60])
            for a in ec.get("analogies", []):
                if isinstance(a, str):
                    analogies.append(a[:60])
                elif isinstance(a, dict):
                    analogies.append(a.get("analogy", "")[:60])

    return {
        "formulas": "\n".join(formulas[:10]) or "None found",
        "code_snippets": "\n".join(code_snippets[:5]) or "None found",
        "key_concepts": ", ".join(list(set(key_concepts))[:15]) or "None found",
        "visual_opportunities": "\n".join(visual_opps[:8]) or "None specified",
        "misconceptions": "\n".join(misconceptions[:5]) or "None found",
        "analogies": "\n".join(analogies[:5]) or "None found",
    }


async def run_course_planner_v4(goal_id: str, user_id: str) -> dict:
    """Run the v4 course planner: structure + parallel storyboards."""
    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")

    def progress(msg: str, pct: int | None = None):
        update = {"current_task": msg}
        if pct is not None:
            update["progress_percentage"] = pct
        try:
            sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
        except Exception:
            pass
        logger.info(f"[CoursePlanner v4] {msg}")

    # Update status
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
        progress("No research data found — run research first", 0)
        sb.table("agent_tasks").update({"status": "failed", "error_message": "Research not completed"}).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
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

    # ── STEP 1: Course Structure ──
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
        logger.error(f"[CoursePlanner v4] Structure generation failed: {e}")
        progress("Structure generation failed", 0)
        sb.table("agent_tasks").update({"status": "failed", "error_message": str(e)}).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
        raise

    # Collect all lessons
    all_lessons = []
    for module in course_structure.get("modules", []):
        for lesson in module.get("lessons", []):
            all_lessons.append(lesson)

    progress(f"Structure ready: {len(course_structure.get('modules', []))} modules, {len(all_lessons)} lessons", 20)

    # ── STEP 2: Parallel storyboard generation ──
    progress(f"Creating visual storyboards for {len(all_lessons)} lessons in parallel...", 25)

    async def generate_lesson_storyboard(lesson: dict) -> dict:
        """Generate visual frame storyboard for one lesson."""
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
            key_concepts=lesson_research["key_concepts"][:200],
            visual_opportunities=lesson_research["visual_opportunities"][:200],
        )

        progress(f"[{lesson_id}] Generating storyboard: {lesson.get('title', '')[:40]}...")

        try:
            # Pass 1: Generate storyboard
            result = await engine.run(
                prompt=prompt,
                system_prompt=LESSON_STORYBOARD_SYSTEM,
                timeout=600,
            )
            storyboard = json.loads(result["result"])
            frames = storyboard.get("frames", [])
            progress(f"[{lesson_id}] Pass 1 done: {len(frames)} frames. Reviewing...")

            # Pass 2: Self-review for pedagogical quality
            review_prompt = STORYBOARD_REVIEW_PROMPT.format(
                lesson_title=lesson.get("title", ""),
                student_name=student_name,
                education_level=profile.get("education_level", "self_learner"),
                storyboard_json=json.dumps(storyboard, indent=2)[:8000],  # Trim to avoid huge prompt
            )

            try:
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
                    progress(f"[{lesson_id}] Review done: {len(review_notes)} fixes applied")
                    for note in review_notes[:3]:
                        logger.info(f"  Review: {note}")
                else:
                    progress(f"[{lesson_id}] Review returned no frames, keeping original")
            except Exception as review_err:
                logger.warning(f"[CoursePlanner v4] Review failed for {lesson_id}: {review_err}")
                progress(f"[{lesson_id}] Review skipped, keeping original storyboard")

            return {
                "lesson_id": lesson_id,
                "title": lesson.get("title", ""),
                "opening_hook": storyboard.get("opening_hook", ""),
                "closing_summary": storyboard.get("closing_summary", []),
                "frames": frames,
                "total_frames": len(frames),
                "total_interactions": sum(1 for f in frames if f.get("interaction")),
                "review_notes": review_notes if 'review_notes' in locals() else [],
            }
        except Exception as e:
            logger.error(f"[CoursePlanner v4] Lesson {lesson_id} failed: {e}")
            progress(f"[{lesson_id}] Failed: {str(e)[:50]}")
            return {
                "lesson_id": lesson_id,
                "title": lesson.get("title", ""),
                "frames": [],
                "error": str(e),
            }

    # Run lessons in batches of 3 to avoid overwhelming Claude's rate limits
    lesson_results = []
    batch_size = 3
    for i in range(0, len(all_lessons), batch_size):
        batch = all_lessons[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(all_lessons) + batch_size - 1) // batch_size
        progress(f"Storyboard batch {batch_num}/{total_batches}: {', '.join(l.get('lesson_id','') for l in batch)}...", 25 + int(50 * i / len(all_lessons)))
        batch_results = await asyncio.gather(
            *[generate_lesson_storyboard(l) for l in batch],
            return_exceptions=True,
        )
        lesson_results.extend(batch_results)

    # Build lesson_plans dict
    lesson_plans = {}
    total_frames = 0
    total_interactions = 0
    for r in lesson_results:
        if isinstance(r, Exception):
            logger.error(f"[CoursePlanner v4] Lesson exception: {r}")
            continue
        if isinstance(r, dict):
            lid = r.get("lesson_id", "")
            lesson_plans[lid] = r
            total_frames += r.get("total_frames", 0)
            total_interactions += r.get("total_interactions", 0)

    progress(f"All storyboards done: {total_frames} frames, {total_interactions} interactions across {len(lesson_plans)} lessons", 85)

    # ── STEP 3: Save to DB ──
    progress("Saving course plan...", 90)

    course_plan = {
        "course_structure": course_structure,
        "lesson_plans": lesson_plans,
        "student_resource_map": {},
        "generation_metadata": {
            "version": 4,
            "engine": "claude_code",
            "total_frames": total_frames,
            "total_interactions": total_interactions,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        sb.table("course_plans").upsert({
            "goal_id": goal_id,
            "user_id": user_id,
            "course_structure": course_structure,
            "lesson_plans": lesson_plans,
            "student_resource_map": {},
            "generation_metadata": course_plan["generation_metadata"],
            "total_lessons": len(lesson_plans),
            "total_modules": len(course_structure.get("modules", [])),
            "total_estimated_minutes": course_structure.get("total_estimated_minutes", 0),
            "version": 4,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="goal_id").execute()
    except Exception as e:
        logger.error(f"[CoursePlanner v4] DB save failed: {e}")
        progress("Failed to save course plan", 0)
        sb.table("agent_tasks").update({"status": "failed", "error_message": str(e)}).eq("goal_id", goal_id).eq("agent_type", "planning").execute()
        raise

    progress(f"Course plan complete! {len(lesson_plans)} lessons, {total_frames} visual frames", 100)
    sb.table("agent_tasks").update({
        "status": "completed",
        "progress_percentage": 100,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("goal_id", goal_id).eq("agent_type", "planning").execute()

    logger.info(
        f"[CoursePlanner v4] DONE: {len(course_structure.get('modules', []))} modules, "
        f"{len(lesson_plans)} lessons, {total_frames} frames, {total_interactions} interactions"
    )

    return course_plan
