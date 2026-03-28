"""
Research Agent v3 — Parallel research via multiple Claude Code subprocesses.

Three-step pipeline:
1. Quick prerequisite gap analysis (no tools, ~30s)
2. 3 PARALLEL Claude Code processes researching different topic groups (~2-3 min each)
3. Merge results + save to DB

Total time: ~3-4 min (vs 30+ min with v2 Pollinations pipeline).
"""

import asyncio
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


async def _research_topic_group(
    engine: ClaudeEngine,
    agent_name: str,
    topics: list[dict],
    context: dict,
    source_target: int,
) -> list[dict]:
    """Run a single research agent for a group of topics. Returns list of sources."""
    if not topics:
        return []

    topic_list = "\n".join(
        f"- {t['topic_name']}" + (f" (reason: {t['why']})" if t.get("why") else "")
        for t in topics
    )

    prompt = SINGLE_AGENT_RESEARCH_PROMPT.format(
        agent_name=agent_name,
        goal_title=context["goal_title"],
        education_level=context["education_level"],
        topic_list=topic_list,
        source_target=source_target,
        fetch_target=min(source_target, 3),
    )

    logger.info(f"[Research v3] {agent_name}: researching {len(topics)} topics, target {source_target} sources")

    result = await engine.run(
        prompt=prompt,
        system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT,
        tools=["WebSearch", "WebFetch"],
        timeout=240,  # 4 min per agent — includes ToolSearch + WebSearch + response gen
        max_turns=10,  # ToolSearch + 3-4 WebSearch + response
    )

    try:
        parsed = json.loads(result["result"])
        sources = parsed.get("sources", [])
        logger.info(f"[Research v3] {agent_name}: found {len(sources)} sources, cost=${result.get('cost_usd', 0):.4f}")
        return sources
    except json.JSONDecodeError as e:
        logger.error(f"[Research v3] {agent_name}: JSON parse error: {e}")
        return []


async def run_research_v3(goal_id: str, user_id: str) -> dict:
    """Run the v3 research pipeline with TRUE parallel execution."""
    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")

    _update_progress(sb, goal_id, "active", 5, "Loading student profile...")

    # Fetch onboarding data
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

    # ── STEP 1: Prerequisite analysis (fast, no tools) ──
    _update_progress(sb, goal_id, "active", 10, "Analyzing prerequisites...")
    logger.info(f"[Research v3] Step 1: Prereq analysis for '{context['goal_title']}'")

    try:
        gap_result = await engine.run(
            prompt=PREREQ_ANALYSIS_PROMPT.format(**context),
            system_prompt="You are an education prerequisite analyst. Return ONLY valid JSON.",
            timeout=90,
        )
        topic_groups = json.loads(gap_result["result"]).get("topic_groups", [])
    except Exception as e:
        logger.warning(f"[Research v3] Prereq analysis failed: {e}")
        topic_groups = [
            {"topic_name": context["goal_title"], "priority": "core",
             "content_needs": {"needs_formulas": True, "needs_code": True,
                               "needs_visual_demo": True, "needs_exercises": True}},
        ]

    prereqs = [t for t in topic_groups if t.get("priority") == "prerequisite"]
    cores = [t for t in topic_groups if t.get("priority") == "core"]
    advanced = [t for t in topic_groups if t.get("priority") == "advanced"]

    logger.info(f"[Research v3] Step 1 done: {len(prereqs)} prereq, {len(cores)} core, {len(advanced)} advanced")

    # ── STEP 2: 3 parallel research agents ──
    _update_progress(sb, goal_id, "active", 20, f"3 agents researching {len(topic_groups)} topics in parallel...")

    # Launch 3 agents in parallel via asyncio.gather
    prereq_task = _research_topic_group(engine, "PREREQUISITE_AGENT", prereqs, context, 4)
    core_task = _research_topic_group(engine, "CORE_AGENT", cores, context, 4)
    advanced_task = _research_topic_group(engine, "ADVANCED_AGENT", advanced or cores[-1:], context, 4)

    prereq_sources, core_sources, advanced_sources = await asyncio.gather(
        prereq_task, core_task, advanced_task,
        return_exceptions=True,
    )

    # Handle exceptions from individual agents
    all_sources = []
    for name, result in [("prereq", prereq_sources), ("core", core_sources), ("advanced", advanced_sources)]:
        if isinstance(result, Exception):
            logger.error(f"[Research v3] {name} agent failed: {result}")
        elif isinstance(result, list):
            all_sources.extend(result)

    if not all_sources:
        _update_progress(sb, goal_id, "failed", 0, error="All research agents failed")
        raise RuntimeError("All research agents failed — no sources found")

    _update_progress(sb, goal_id, "active", 75, f"Found {len(all_sources)} sources, synthesizing...")

    # ── STEP 3: Quick synthesis ──
    synthesis_prompt = f"""Given these {len(all_sources)} research sources about "{context['goal_title']}", create a synthesis.

Return ONLY valid JSON:
{{
  "gaps": [{{"topic": "string", "missing_content": "string", "severity": "critical"|"moderate"|"minor"}}],
  "teaching_notes": {{"topic_name": "specific teaching guidance"}},
  "cross_topic_formulas": [{{"formula_latex": "string", "formula_plain_spoken": "string", "topic": "string", "importance": "string"}}],
  "demo_codebases": [{{"url": "string", "name": "string", "description": "string", "language": "string", "suitability_score": 0.9}}],
  "coding_exercises": [{{"title": "string", "description": "string", "difficulty": "beginner"|"intermediate"|"advanced", "topic": "string"}}]
}}

Topics covered: {', '.join(t['topic_name'] for t in topic_groups)}
Sources found: {len(all_sources)} across {len(set(s.get('topic_group','') for s in all_sources))} topics
Sample source titles: {', '.join(s.get('title','')[:40] for s in all_sources[:5])}
"""

    try:
        synth_result = await engine.run(
            prompt=synthesis_prompt,
            system_prompt="You are a research synthesizer. Analyze coverage and create teaching guidance. Return ONLY JSON.",
            timeout=120,
        )
        synthesis = json.loads(synth_result["result"])
    except Exception as e:
        logger.warning(f"[Research v3] Synthesis failed: {e}, using empty")
        synthesis = {"gaps": [], "teaching_notes": {}, "cross_topic_formulas": [], "demo_codebases": [], "coding_exercises": []}

    # ── STEP 4: Save to DB ──
    _update_progress(sb, goal_id, "active", 85, "Saving to database...")

    parsed = {
        "topic_tree": {"effort_tier": "standard", "topic_groups": topic_groups},
        "sources": all_sources,
        "synthesis": synthesis,
    }

    await _save_results(sb, goal_id, user_id, parsed)
    await _save_sources(sb, goal_id, user_id, all_sources)

    formula_count = sum(len(s.get("formulas", [])) for s in all_sources)
    visual_count = sum(1 for s in all_sources if s.get("visual_opportunity"))
    logger.info(
        f"[Research v3] COMPLETE: {len(topic_groups)} topics ({len(prereqs)} prereq), "
        f"{len(all_sources)} sources, {formula_count} formulas, {visual_count} visuals"
    )

    _update_progress(sb, goal_id, "completed", 100, "Research complete!")
    return parsed


async def _save_results(sb, goal_id: str, user_id: str, parsed: dict):
    """Save to research_results table."""
    synthesis = parsed.get("synthesis", {})
    sb.table("research_results").upsert({
        "goal_id": goal_id,
        "user_id": user_id,
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
    """Save to research_sources table."""
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
            "metadata": {"formula_plain_spoken": [f.get("formula_plain_spoken", "") for f in source.get("formulas", [])] if source.get("formulas") else []},
        }
        try:
            sb.table("research_sources").insert(row).execute()
        except Exception as e:
            logger.warning(f"[Research v3] Save source failed: {e}")


def _update_progress(sb, goal_id, status, pct, task="", error=""):
    update = {"status": status, "progress_percentage": pct, "current_task": task}
    if status == "active" and pct == 5:
        update["started_at"] = datetime.now(timezone.utc).isoformat()
    if status == "completed":
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
    if error:
        update["error_message"] = error
    try:
        sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "research").execute()
    except Exception:
        pass
