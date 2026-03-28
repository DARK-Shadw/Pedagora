"""
Research Agent v3 — Production quality, real-time progress updates.

Pipeline:
1. Quick prerequisite gap analysis (~30s)
2. Sequential research agents with live progress:
   - Prerequisites: 6 sources (~2-3 min)
   - Core topics: 8 sources (~3-4 min)
   - Advanced topics: 6 sources (~2-3 min)
3. Quick synthesis (~30s)
4. Save to DB

Total: ~8-10 min with real-time status updates.
"""

import json
import logging
from datetime import datetime, timezone

from app.engine.claude_engine import ClaudeEngine
from app.agents.research_prompts_v3 import (
    PREREQ_ANALYSIS_PROMPT,
    SINGLE_AGENT_RESEARCH_PROMPT,
    RESEARCH_AGENT_SYSTEM_PROMPT,
)
from app.services.agent_task import fetch_onboarding_data
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


def build_student_context(onboarding: dict) -> dict:
    """Build rich student context from onboarding data."""
    goal = onboarding.get("goal", {})
    prefs = onboarding.get("preferences", {})
    profile = onboarding.get("profile", {})
    prereqs = onboarding.get("prerequisites", [])
    assessments = onboarding.get("assessments", [])

    prereqs_text = "None provided"
    if prereqs:
        prereqs_text = "\n".join(
            f"- {p.get('skill_name', '?')}: confidence={p.get('confidence_level', '?')}"
            + (f" -- {p['notes']}" if p.get("notes") else "")
            for p in prereqs
        )

    assessments_text = "No assessment completed"
    if assessments:
        assessments_text = "\n".join(
            f"- Q: \"{a.get('question', '?')}\" => {a.get('confidence_level', '?')}"
            for a in assessments
        )

    return {
        "goal_title": goal.get("title", "Unknown"),
        "end_goal": goal.get("end_goal", "Not specified"),
        "motivation": goal.get("motivation", "Not specified"),
        "is_exam_prep": goal.get("is_exam_prep", False),
        "education_level": profile.get("education_level", "self_learner"),
        "learning_style": prefs.get("learning_style", "visual"),
        "learning_style_note": prefs.get("learning_style_note", ""),
        "content_depth": prefs.get("content_depth", "intermediate"),
        "content_depth_note": prefs.get("content_depth_note", ""),
        "teaching_style": prefs.get("teaching_style", "lecture"),
        "prerequisites_text": prereqs_text,
        "assessments_text": assessments_text,
    }


async def _research_with_progress(
    engine: ClaudeEngine,
    agent_name: str,
    topics: list[dict],
    context: dict,
    source_target: int,
    progress_fn,
) -> list[dict]:
    """Run a research agent with real-time progress updates via streaming."""
    if not topics:
        return []

    topic_list = "\n".join(
        f"- {t['topic_name']}" + (f" (reason: {t.get('why', '')})" if t.get("why") else "")
        for t in topics
    )

    prompt = SINGLE_AGENT_RESEARCH_PROMPT.format(
        agent_name=agent_name,
        goal_title=context["goal_title"],
        education_level=context["education_level"],
        topic_list=topic_list,
        source_target=source_target,
    )

    system = RESEARCH_AGENT_SYSTEM_PROMPT
    progress_fn(f"[{agent_name}] Starting research on {len(topics)} topics...")

    final_text = ""
    search_count = 0
    fetch_count = 0

    async for event in engine.stream(
        prompt=prompt,
        system_prompt=system,
        max_turns=15,
        timeout=480,  # 8 min per agent — video topics need more searches
    ):
        if event["type"] == "tool_use":
            name = event.get("name", "")
            inp = event.get("input", {})

            if "WebSearch" in name or "web_search" in name.lower():
                query = inp.get("query", "")
                search_count += 1
                progress_fn(f"[{agent_name}] Searching: {query[:60]}")
            elif "WebFetch" in name or "web_fetch" in name.lower():
                url = inp.get("url", "")
                fetch_count += 1
                progress_fn(f"[{agent_name}] Reading: {url[:65]}")
            elif "ToolSearch" in name:
                pass  # Internal tool discovery, ignore
            else:
                progress_fn(f"[{agent_name}] Using: {name}")

        elif event["type"] == "text":
            final_text = event.get("content", "")

        elif event["type"] == "result":
            final_text = event.get("result", "") or final_text
            cost = event.get("cost_usd", 0)
            logger.info(f"[Research v3] {agent_name}: done, {search_count} searches, {fetch_count} fetches, cost=${cost:.4f}")

        elif event["type"] == "error":
            logger.error(f"[Research v3] {agent_name}: {event.get('message', 'unknown error')}")
            progress_fn(f"[{agent_name}] Error: {event.get('message', '')[:50]}")
            return []

    # Parse sources from response
    stripped = final_text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        elif lines[0].startswith("```"):
            lines = lines[1:]
        stripped = "\n".join(lines).strip()

    try:
        parsed = json.loads(stripped)
        sources = parsed.get("sources", [])
        progress_fn(f"[{agent_name}] Found {len(sources)} sources")
        return sources
    except json.JSONDecodeError as e:
        logger.error(f"[Research v3] {agent_name}: JSON parse failed: {e}")
        logger.error(f"[Research v3] Raw: {stripped[:300]}")
        progress_fn(f"[{agent_name}] Failed to parse results")
        return []


async def run_research_v3(goal_id: str, user_id: str) -> dict:
    """Run production research pipeline with real-time progress."""
    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")

    def progress(msg: str, pct: int | None = None):
        """Update progress in DB — visible to frontend via polling."""
        update = {"current_task": msg}
        if pct is not None:
            update["progress_percentage"] = pct
        try:
            sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "research").execute()
        except Exception:
            pass
        logger.info(f"[Research v3] {msg}")

    _update_status(sb, goal_id, "active", 2, "Loading student profile...")

    # ── Fetch onboarding data ──
    try:
        onboarding = await fetch_onboarding_data(goal_id, user_id)
    except Exception as e:
        logger.warning(f"[Research v3] Onboarding error: {e}")
        onboarding = {"goal": {}, "preferences": {}, "profile": {}, "prerequisites": [], "assessments": []}
        try:
            row = sb.table("learning_goals").select("title, end_goal, motivation, is_exam_prep").eq("id", goal_id).single().execute()
            if row.data:
                onboarding["goal"] = row.data
        except Exception:
            pass

    context = build_student_context(onboarding)
    progress(f"Analyzing prerequisites for: {context['goal_title'][:50]}...", 5)

    # ── STEP 1: Prerequisite gap analysis ──
    try:
        gap_result = await engine.run(
            prompt=PREREQ_ANALYSIS_PROMPT.format(**context),
            system_prompt="You are an education prerequisite analyst. Return ONLY valid JSON.",
            timeout=90,
        )
        topic_groups = json.loads(gap_result["result"]).get("topic_groups", [])
    except Exception as e:
        logger.warning(f"[Research v3] Prereq analysis failed: {e}")
        topic_groups = [{"topic_name": context["goal_title"], "priority": "core",
                         "content_needs": {"needs_formulas": True, "needs_code": True,
                                           "needs_visual_demo": True, "needs_exercises": True}}]

    prereqs = [t for t in topic_groups if t.get("priority") == "prerequisite"]
    cores = [t for t in topic_groups if t.get("priority") == "core"]
    advanced = [t for t in topic_groups if t.get("priority") == "advanced"]

    progress(f"Found {len(topic_groups)} topics: {len(prereqs)} prerequisite, {len(cores)} core, {len(advanced)} advanced", 10)
    for t in topic_groups:
        logger.info(f"  [{t.get('priority')}] {t.get('topic_name')}")

    # ── STEP 2: Parallel research agents with live progress ──
    import asyncio

    def make_progress_fn(name):
        """Create a progress callback for an agent."""
        def fn(msg):
            progress(msg)  # All agents update the same DB field
        return fn

    progress(f"Launching parallel research agents...", 15)

    tasks = []
    if prereqs:
        tasks.append(_research_with_progress(engine, "PREREQUISITES", prereqs, context, 10, make_progress_fn("PREREQ")))
    if cores:
        tasks.append(_research_with_progress(engine, "CORE", cores, context, 12, make_progress_fn("CORE")))
    if advanced:
        tasks.append(_research_with_progress(engine, "ADVANCED", advanced, context, 8, make_progress_fn("ADVANCED")))
    elif len(cores) > 3:
        mid = len(cores) // 2
        tasks.append(_research_with_progress(engine, "CORE_A", cores[:mid], context, 8, make_progress_fn("CORE_A")))
        tasks.append(_research_with_progress(engine, "CORE_B", cores[mid:], context, 8, make_progress_fn("CORE_B")))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_sources = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[Research v3] Agent failed: {r}")
        elif isinstance(r, list):
            all_sources.extend(r)

    progress(f"All agents done: {len(all_sources)} sources total", 75)

    if not all_sources:
        _update_status(sb, goal_id, "failed", 0, error="No sources found from any agent")
        raise RuntimeError("All research agents returned 0 sources")

    # ── STEP 3: Quick synthesis ──
    progress(f"Synthesizing {len(all_sources)} sources...", 82)

    topic_names = [t["topic_name"] for t in topic_groups]
    source_titles = [s.get("title", "")[:40] for s in all_sources[:8]]

    try:
        synth_result = await engine.run(
            prompt=f"""Synthesize these {len(all_sources)} research sources about "{context['goal_title']}".

Topics covered: {', '.join(topic_names)}
Source titles: {', '.join(source_titles)}

Return ONLY valid JSON:
{{"gaps": [{{"topic": "...", "missing_content": "...", "severity": "critical"|"moderate"|"minor"}}],
"teaching_notes": {{"topic_name": "specific guidance"}},
"cross_topic_formulas": [{{"formula_latex": "...", "formula_plain_spoken": "...", "topic": "...", "importance": "..."}}],
"demo_codebases": [{{"url": "...", "name": "...", "description": "...", "language": "python", "suitability_score": 0.9}}],
"coding_exercises": [{{"title": "...", "description": "...", "difficulty": "beginner"|"intermediate"|"advanced", "topic": "..."}}]}}""",
            system_prompt="You are a research synthesizer. Return ONLY valid JSON.",
            timeout=180,  # 3 min for synthesis
        )
        synthesis = json.loads(synth_result["result"])
    except Exception as e:
        logger.warning(f"[Research v3] Synthesis failed: {e}")
        synthesis = {"gaps": [], "teaching_notes": {}, "cross_topic_formulas": [],
                     "demo_codebases": [], "coding_exercises": []}

    # ── STEP 4: Save to DB ──
    progress("Saving results to database...", 90)

    parsed = {
        "topic_tree": {"effort_tier": "standard", "topic_groups": topic_groups},
        "sources": all_sources,
        "synthesis": synthesis,
    }

    await _save_results(sb, goal_id, user_id, parsed)
    await _save_sources(sb, goal_id, user_id, all_sources)

    formula_count = sum(len(s.get("formulas", [])) for s in all_sources)
    visual_count = sum(1 for s in all_sources if s.get("visual_opportunity"))

    progress(
        f"Research complete! {len(all_sources)} sources, {formula_count} formulas, "
        f"{visual_count} visuals across {len(topic_groups)} topics",
        100,
    )
    _update_status(sb, goal_id, "completed", 100)

    logger.info(
        f"[Research v3] DONE: {len(topic_groups)} topics ({len(prereqs)} prereq), "
        f"{len(all_sources)} sources, {formula_count} formulas"
    )
    return parsed


async def _save_results(sb, goal_id: str, user_id: str, parsed: dict):
    synthesis = parsed.get("synthesis", {})
    sb.table("research_results").upsert({
        "goal_id": goal_id, "user_id": user_id,
        "topic_tree": parsed.get("topic_tree", {}),
        "synthesis": synthesis,
        "source_count": len(parsed.get("sources", [])),
        "teaching_notes": synthesis.get("teaching_notes"),
        "demo_codebases": synthesis.get("demo_codebases"),
        "coding_exercises": synthesis.get("coding_exercises"),
        "cross_topic_formulas": synthesis.get("cross_topic_formulas"),
        "version": 3,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="goal_id").execute()


async def _save_sources(sb, goal_id: str, user_id: str, sources: list):
    sb.table("research_sources").delete().eq("goal_id", goal_id).execute()
    for source in sources:
        row = {
            "goal_id": goal_id, "user_id": user_id,
            "topic_group": source.get("topic_group", ""),
            "source_type": source.get("source_type", "article"),
            "title": source.get("title", ""),
            "url": source.get("url", ""),
            "author": source.get("author"),
            "summary": source.get("summary", ""),
            "key_concepts": source.get("key_concepts", []),
            "relevance_score": source.get("relevance_score", 0.5),
            "credibility_score": source.get("credibility_score", 0.5),
            "difficulty_level": source.get("difficulty_level", "intermediate"),
            "formulas": source.get("formulas"),
            "code_snippets": source.get("code_snippets"),
            "extracted_content": {
                "analogies": source.get("analogies", []),
                "misconceptions": source.get("misconceptions", []),
                "visual_opportunity": source.get("visual_opportunity", ""),
            },
            "metadata": {
                "formula_plain_spoken": [
                    f.get("formula_plain_spoken", "") for f in source.get("formulas", [])
                ] if source.get("formulas") else [],
            },
        }
        try:
            sb.table("research_sources").insert(row).execute()
        except Exception as e:
            logger.warning(f"[Research v3] Save source failed: {e}")


def _update_status(sb, goal_id, status, pct, task="", error=""):
    update = {"status": status, "progress_percentage": pct, "current_task": task}
    if status == "active" and pct <= 5:
        update["started_at"] = datetime.now(timezone.utc).isoformat()
    if status == "completed":
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
    if error:
        update["error_message"] = error
    try:
        sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "research").execute()
    except Exception:
        pass
