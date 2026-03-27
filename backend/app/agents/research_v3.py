"""
Research Agent v3 — Claude Code powered research pipeline.

Replaces the 5-stage Pollinations pipeline with a single Claude Code call.
Uses WebSearch + WebFetch tools for comprehensive research with prerequisite
detection based on student assessment data.
"""

import json
import logging
from datetime import datetime, timezone

from app.engine.claude_engine import ClaudeEngine
from app.agents.research_prompts_v3 import RESEARCH_V3_SYSTEM_PROMPT, RESEARCH_V3_PROMPT
from app.services.agent_task import fetch_onboarding_data
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


def build_student_context(onboarding: dict) -> dict:
    """Build rich student context from onboarding data for the prompt."""
    goal = onboarding.get("goal", {})
    prefs = onboarding.get("preferences", {})
    profile = onboarding.get("profile", {})
    prereqs = onboarding.get("prerequisites", [])
    assessments = onboarding.get("assessments", [])

    # Format prerequisites as readable text
    prereqs_text = "None provided"
    if prereqs:
        lines = []
        for p in prereqs:
            lines.append(
                f"- {p.get('skill_name', '?')}: "
                f"confidence={p.get('confidence_level', '?')}"
                f"{' — ' + p['notes'] if p.get('notes') else ''}"
            )
        prereqs_text = "\n".join(lines)

    # Format assessment results as readable text
    assessments_text = "No assessment completed"
    if assessments:
        lines = []
        for a in assessments:
            lines.append(
                f"- Q: \"{a.get('question', '?')}\" "
                f"=> Student confidence: {a.get('confidence_level', '?')}"
            )
        assessments_text = "\n".join(lines)

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


async def run_research_v3(goal_id: str, user_id: str) -> dict:
    """
    Run the v3 research pipeline using Claude Code.

    Args:
        goal_id: The learning goal ID
        user_id: The user ID

    Returns:
        Parsed research result dict
    """
    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")

    # Update task status
    _update_progress(sb, goal_id, "active", 5, "Loading student profile...")

    # Fetch all onboarding data
    try:
        onboarding = await fetch_onboarding_data(goal_id, user_id)
    except Exception as e:
        logger.warning(f"[Research v3] Onboarding data error: {e}, using defaults")
        onboarding = {
            "goal": {"title": "Unknown topic"},
            "preferences": {},
            "profile": {},
            "prerequisites": [],
            "assessments": [],
        }
        # Try to at least get the goal title
        try:
            goal_row = sb.table("learning_goals").select("title, end_goal, motivation, is_exam_prep").eq("id", goal_id).single().execute()
            if goal_row.data:
                onboarding["goal"] = goal_row.data
        except Exception:
            pass

    context = build_student_context(onboarding)
    _update_progress(sb, goal_id, "active", 10, "Starting research with Claude...")

    # Build the prompt
    prompt = RESEARCH_V3_PROMPT.format(**context)

    logger.info(f"[Research v3] Starting research for goal={goal_id}, topic='{context['goal_title']}'")

    # Run Claude Code
    try:
        result = await engine.run(
            prompt=prompt,
            system_prompt=RESEARCH_V3_SYSTEM_PROMPT,
            tools=["WebSearch", "WebFetch"],
            timeout=300,  # 5 min max
            max_turns=30,  # Allow plenty of tool calls for thorough research
        )
    except Exception as e:
        logger.error(f"[Research v3] Claude Code failed: {e}")
        _update_progress(sb, goal_id, "failed", 0, error=str(e))
        raise

    _update_progress(sb, goal_id, "active", 80, "Parsing research results...")

    # Parse the result
    try:
        parsed = json.loads(result["result"])
    except json.JSONDecodeError as e:
        logger.error(f"[Research v3] Failed to parse JSON: {e}")
        logger.error(f"[Research v3] Raw result: {result['result'][:500]}")
        _update_progress(sb, goal_id, "failed", 0, error=f"JSON parse error: {e}")
        raise

    # Validate structure
    if "topic_tree" not in parsed or "sources" not in parsed:
        error = "Missing required fields: topic_tree, sources"
        logger.error(f"[Research v3] {error}")
        _update_progress(sb, goal_id, "failed", 0, error=error)
        raise ValueError(error)

    _update_progress(sb, goal_id, "active", 85, "Saving research results...")

    # Save to database
    await _save_results(sb, goal_id, user_id, parsed)
    await _save_sources(sb, goal_id, user_id, parsed.get("sources", []))

    # Log stats
    topic_count = len(parsed.get("topic_tree", {}).get("topic_groups", []))
    source_count = len(parsed.get("sources", []))
    prereq_topics = sum(
        1 for t in parsed.get("topic_tree", {}).get("topic_groups", [])
        if t.get("priority") == "prerequisite"
    )
    formula_count = sum(
        len(s.get("formulas", []))
        for s in parsed.get("sources", [])
    )

    logger.info(
        f"[Research v3] Complete: {topic_count} topics ({prereq_topics} prereq), "
        f"{source_count} sources, {formula_count} formulas, "
        f"cost=${result.get('cost_usd', 0):.4f}"
    )

    _update_progress(sb, goal_id, "completed", 100, "Research complete!")

    return parsed


async def _save_results(sb, goal_id: str, user_id: str, parsed: dict):
    """Save research results to research_results table."""
    topic_tree = parsed.get("topic_tree", {})
    synthesis = parsed.get("synthesis", {})

    sb.table("research_results").upsert({
        "goal_id": goal_id,
        "user_id": user_id,
        "topic_tree": topic_tree,
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
    """Save research sources to research_sources table."""
    # Delete old sources for this goal
    sb.table("research_sources").delete().eq("goal_id", goal_id).execute()

    # Insert new sources
    for source in sources:
        row = {
            "goal_id": goal_id,
            "user_id": user_id,
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
                    f.get("formula_plain_spoken", "")
                    for f in source.get("formulas", [])
                ],
            },
        }
        try:
            sb.table("research_sources").insert(row).execute()
        except Exception as e:
            logger.warning(f"[Research v3] Failed to save source '{source.get('title', '?')}': {e}")


def _update_progress(sb, goal_id: str, status: str, pct: int, task: str = "", error: str = ""):
    """Update agent_tasks progress."""
    update = {
        "status": status,
        "progress_percentage": pct,
        "current_task": task,
    }
    if status == "active" and pct == 5:
        update["started_at"] = datetime.now(timezone.utc).isoformat()
    if status == "completed":
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
    if error:
        update["error_message"] = error

    try:
        sb.table("agent_tasks").update(update).eq("goal_id", goal_id).eq("agent_type", "research").execute()
    except Exception as e:
        logger.warning(f"[Research v3] Progress update failed: {e}")
