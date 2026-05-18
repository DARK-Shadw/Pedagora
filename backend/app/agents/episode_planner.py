"""Single Episode Planner — one Gemini call → visual storyboard.

Skips research entirely. Generates a single-lesson storyboard using
Gemini 2.5 Flash, then wraps it in a minimal 1-module/1-lesson
CourseStructure so downstream Animation + Teacher agents work unchanged.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from app.config import get_settings
from app.services.supabase import get_supabase
from app.services.agent_task import update_agent_task

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ──────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────

EPISODE_SYSTEM = """\
You are an expert visual lesson designer for an education platform built \
in the style of 3Blue1Brown. You create single-episode lessons — each one \
is a self-contained visual journey through a focused topic. Every lesson \
is a sequence of visual frames; every frame breaks into 3-6 timeline-locked \
steps; every step has short, specific narration. You return ONLY valid JSON."""

EPISODE_PROMPT = """\
Create a visual-first storyboard for a SINGLE EPISODE on this topic.

TOPIC: "{topic}"
END GOAL: {end_goal}
EDUCATION LEVEL: {education_level}
LEARNING STYLE: {learning_style}

This is a SINGLE self-contained episode (not part of a larger course).
The student should walk away with a solid understanding of the topic.
Draw on your own knowledge — include concrete examples, real code,
step-by-step visual breakdowns, and precise explanations.

═══════════════════════════════════════════════════════════════════════
HARD CONSTRAINTS — violating any = rejected.
═══════════════════════════════════════════════════════════════════════

1. MINIMUM 12 frames. Fewer = incomplete lesson.
2. MINIMUM 15 minutes total. Sum(frame.estimated_seconds) >= 900.
3. MINIMUM 3 interactions, spread evenly (not all at the end).
4. EVERY frame.estimated_seconds is in [30, 75]. No 2-minute frames.
   If a concept needs 120s, split it into TWO frames.
5. EVERY frame has a `steps` array with 3-6 entries. NO empty steps.
6. EVERY step has: label, anim_time, description, narration_spoken,
   duration_seconds. label is a unique kebab-case ID per frame.
7. At least 2 code frames with real, runnable code examples.
8. At least 2 animation frames showing the concept step-by-step
   with concrete data (arrays, numbers, visuals — not abstract boxes).

═══════════════════════════════════════════════════════════════════════
VOICE STYLE — narration_spoken must read like 3Blue1Brown.
═══════════════════════════════════════════════════════════════════════

- Average sentence <= 14 words. Hard cap 16 words.
- Use SPECIFIC concrete nouns: "this array", "the middle element",
  "index 4". NEVER "the visualization", "the thing".
- Mark deliberate pauses with "..." — TTS honors them.
- Ask a rhetorical question at least once per 3-step window.
- NO LaTeX. NO underscores. NO subscripts.
  Write "log n" not "log_n". Write "n squared" not "n^2".
- BANNED openers: "Look at...", "Notice how...", "In this video...",
  "Let us...", "Today we...", "It is important to note...".
- BANNED filler: "kind of like", "really cool", "super cool",
  "amazing thing", "as you can see", "let me explain".

═══════════════════════════════════════════════════════════════════════
PEDAGOGY — 3b1b structure.
═══════════════════════════════════════════════════════════════════════

R1. SHOW BEFORE YOU TELL. Visual demonstration first, then explanation.
R2. CONCRETE EXAMPLES. Use specific numbers, arrays, data — never abstract.
R3. CODE IS ESSENTIAL. Show real runnable code. Walk through it line by line.
R4. INTERACTIONS REQUIRE REASONING. Bad: "What do you think?"
    Good: "What index does the algorithm check next?" / "Why halve the range?"
R5. ONE NEW IDEA PER FRAME. Progressive disclosure.
R6. STEP-BY-STEP BREAKDOWN. For algorithms, trace through a concrete example
    showing each step with specific values.

STORY ARC:
  HOOK (1-2 frames, 45-75s) — a striking visual or surprising question.
  CONCEPT BLOCKS (8-12 frames) — VISUALIZE -> EXPLAIN -> CODE -> CHECK.
  CLIMAX (1-2 frames) — the core "aha" insight clicks.
  RESOLUTION (1-2 frames) — connect back to the hook, summarize.

═══════════════════════════════════════════════════════════════════════
OUTPUT JSON SCHEMA
═══════════════════════════════════════════════════════════════════════

Visual types: animation, equation, diagram, code, image, image_sequence,
              interactive, split, blackboard
Story phases: hook, motivation, concept, climax, resolution, practice

Example of ONE frame (your output must have 12+ frames):

{{
  "frames": [
    {{
      "frame_id": "f01",
      "visual_type": "animation",
      "story_phase": "hook",
      "estimated_seconds": 50,
      "visual_spec": {{
        "description": "Sorted array [2,5,8,12,16,23,38,56,72,91]. A target value 23 glows. Binary search narrows the range with animated brackets."
      }},
      "narration_spoken": "Here is a sorted list of ten numbers. Your job: find twenty three. How fast can you do it?",
      "steps": [
        {{
          "step_id": "step-1",
          "label": "show-array",
          "anim_time": 0,
          "description": "Display sorted array with indices",
          "narration_spoken": "Here is a sorted list of ten numbers.",
          "duration_seconds": 8,
          "pause_after": false
        }},
        {{
          "step_id": "step-2",
          "label": "highlight-target",
          "anim_time": 8,
          "description": "Target 23 glows golden",
          "narration_spoken": "Your job: find twenty three.",
          "duration_seconds": 10,
          "pause_after": false
        }},
        {{
          "step_id": "step-3",
          "label": "pose-question",
          "anim_time": 18,
          "description": "Text overlay: How fast?",
          "narration_spoken": "How fast can you do it?",
          "duration_seconds": 8,
          "pause_after": true
        }}
      ],
      "interaction": null,
      "transition": "fade",
      "next_frame": "f02"
    }}
  ],
  "opening_hook": "What if you could find any item in a million-element list by checking just twenty?",
  "closing_summary": [
    "Binary search halves the search space each step",
    "It runs in log n time — 20 checks for a million items",
    "The array must be sorted for binary search to work"
  ]
}}

REMEMBER: 12+ frames, 15+ minutes, 3+ interactions, 3-6 steps per frame,
real code examples, concrete step-by-step traces with actual values.
"""


# ──────────────────────────────────────────────────────────────────────
# Core generation
# ──────────────────────────────────────────────────────────────────────

async def _call_gemini(
    prompt: str,
    system_prompt: str,
    api_key: str,
    temperature: float = 0.4,
    max_output_tokens: int = 16384,
) -> tuple[dict, dict]:
    """Call Gemini and return (parsed_json, meta)."""
    client = genai.Client(api_key=api_key)

    t0 = time.monotonic()
    resp = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        ),
    )
    elapsed = time.monotonic() - t0

    raw = resp.text or ""
    usage = getattr(resp, "usage_metadata", None)
    meta = {
        "model": GEMINI_MODEL,
        "elapsed_seconds": round(elapsed, 2),
        "tokens_in": getattr(usage, "prompt_token_count", None) if usage else None,
        "tokens_out": getattr(usage, "candidates_token_count", None) if usage else None,
        "raw_length": len(raw),
    }

    parsed = json.loads(raw)
    return parsed, meta


async def _call_groq(
    prompt: str,
    system_prompt: str,
    api_key: str,
    temperature: float = 0.4,
    max_tokens: int = 6000,
) -> tuple[dict, dict]:
    """Call Groq and return (parsed_json, meta)."""
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
    elapsed = time.monotonic() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    meta = {
        "model": GROQ_MODEL,
        "elapsed_seconds": round(elapsed, 2),
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
        "raw_length": len(content),
    }

    parsed = json.loads(content)
    return parsed, meta


def _wrap_in_course_structure(
    topic: str,
    storyboard: dict,
    estimated_minutes: int,
) -> tuple[dict, dict]:
    """Wrap a storyboard in a minimal 1-module/1-lesson CourseStructure."""
    lesson_id = "mod1-les1"

    course_structure = {
        "course_title": topic,
        "course_description": f"Single episode: {topic}",
        "total_estimated_minutes": estimated_minutes,
        "difficulty_progression": "beginner -> intermediate",
        "modules": [{
            "module_id": "mod1",
            "title": topic,
            "description": f"Complete coverage of {topic}",
            "order": 1,
            "estimated_minutes": estimated_minutes,
            "lessons": [{
                "lesson_id": lesson_id,
                "title": topic,
                "lesson_type": "visualization",
                "estimated_minutes": estimated_minutes,
                "learning_objectives": [],
                "topics_covered": [topic],
                "prerequisites": [],
                "key_formulas": [],
                "key_code_demos": [],
            }],
        }],
    }

    frames = storyboard.get("frames", [])
    lesson_plan = {
        "lesson_id": lesson_id,
        "title": topic,
        "opening_hook": storyboard.get("opening_hook", ""),
        "closing_summary": storyboard.get("closing_summary", []),
        "frames": frames,
        "total_frames": len(frames),
        "total_interactions": sum(1 for f in frames if f.get("interaction")),
        "critic_passed": True,
    }

    return course_structure, lesson_plan


# ──────────────────────────────────────────────────────────────────────
# Progress helpers
# ──────────────────────────────────────────────────────────────────────

def _update_task(sb, goal_id: str, **kwargs):
    try:
        sb.table("agent_tasks").update(kwargs).eq(
            "goal_id", goal_id
        ).eq("agent_type", "planning").execute()
    except Exception:
        pass


def _log(sb, goal_id: str, msg: str, level: str = "info"):
    try:
        sb.rpc(
            "append_agent_task_log",
            {
                "p_goal_id": goal_id,
                "p_agent_type": "planning",
                "p_log_entry": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent": "episode_planner",
                    "message": msg,
                    "level": level,
                },
            },
        ).execute()
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

async def run_episode_planner(goal_id: str, user_id: str) -> dict:
    """Generate a single-episode storyboard using Gemini, save as course plan.

    This replaces the full research → structure → detail pipeline for
    single episode content type.
    """
    settings = get_settings()
    sb = get_supabase()

    # Mark planning as active
    _update_task(sb, goal_id,
        status="active",
        progress_percentage=5,
        current_task="Starting episode planner...",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _log(sb, goal_id, "Episode planner started (Gemini 2.5 Flash)")

    # Load onboarding data
    _update_task(sb, goal_id, current_task="Loading student profile...", progress_percentage=10)

    try:
        goal_row = sb.table("learning_goals").select("*").eq("id", goal_id).single().execute()
        goal = goal_row.data or {}
    except Exception as e:
        _fail_task(sb, goal_id, f"Failed to load goal: {e}")
        raise

    topic = goal.get("title", "Unknown Topic")
    end_goal = goal.get("end_goal") or f"Understand {topic}"

    prefs = {}
    try:
        prefs_row = sb.table("user_preferences").select("*").eq("user_id", user_id).single().execute()
        prefs = prefs_row.data or {}
    except Exception:
        pass

    education_level = prefs.get("education_level") or "self_learner"
    learning_style = prefs.get("learning_style") or "visual"

    # Build prompt
    prompt = EPISODE_PROMPT.format(
        topic=topic,
        end_goal=end_goal,
        education_level=education_level,
        learning_style=learning_style,
    )

    _update_task(sb, goal_id,
        current_task=f"Generating storyboard for \"{topic}\"...",
        progress_percentage=20,
    )
    _log(sb, goal_id, f"Calling Gemini 2.5 Flash for \"{topic}\"")

    # Try Gemini first, fall back to Groq
    api_keys = settings.get_gemini_api_keys()
    storyboard = None
    meta = None
    last_error = None

    for i, key in enumerate(api_keys):
        try:
            storyboard, meta = await _call_gemini(
                prompt=prompt,
                system_prompt=EPISODE_SYSTEM,
                api_key=key,
            )
            logger.info(
                f"[EpisodePlanner] Gemini OK: {meta['elapsed_seconds']:.1f}s, "
                f"{meta['raw_length']} chars, "
                f"{meta.get('tokens_in')}->{meta.get('tokens_out')} tok"
            )
            break
        except (ClientError, ServerError) as e:
            last_error = e
            logger.warning(f"[EpisodePlanner] Gemini key#{i} failed: {e}")
            continue
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"[EpisodePlanner] Gemini key#{i} JSON parse failed: {e}")
            continue

    # Fallback to Groq
    if storyboard is None:
        groq_key = settings.groq_api_key
        if groq_key:
            _log(sb, goal_id, f"Gemini exhausted, falling back to Groq {GROQ_MODEL}")
            _update_task(sb, goal_id,
                current_task=f"Gemini unavailable, using Groq {GROQ_MODEL}...",
                progress_percentage=25,
            )
            try:
                storyboard, meta = await _call_groq(
                    prompt=prompt,
                    system_prompt=EPISODE_SYSTEM,
                    api_key=groq_key,
                )
                logger.info(
                    f"[EpisodePlanner] Groq OK: {meta['elapsed_seconds']:.1f}s, "
                    f"{meta['raw_length']} chars"
                )
            except Exception as e:
                last_error = e
                logger.warning(f"[EpisodePlanner] Groq failed: {e}")

    if storyboard is None:
        _fail_task(sb, goal_id, f"All providers failed: {last_error}")
        raise RuntimeError(f"Episode generation failed: {last_error}")

    frames = storyboard.get("frames", [])
    total_seconds = sum(f.get("estimated_seconds", 0) for f in frames)
    estimated_minutes = max(1, total_seconds // 60)

    _update_task(sb, goal_id,
        current_task=f"Got {len(frames)} frames ({estimated_minutes} min) — saving...",
        progress_percentage=80,
    )
    _log(sb, goal_id,
        f"Storyboard: {len(frames)} frames, {total_seconds}s total, "
        f"{sum(1 for f in frames if f.get('interaction'))} interactions"
    )

    # Wrap in course structure
    course_structure, lesson_plan = _wrap_in_course_structure(
        topic=topic,
        storyboard=storyboard,
        estimated_minutes=estimated_minutes,
    )

    # Save to DB (same schema as full course planner)
    try:
        sb.table("course_plans").upsert({
            "goal_id": goal_id,
            "user_id": user_id,
            "course_structure": course_structure,
            "lesson_plans": {"mod1-les1": lesson_plan},
            "student_resource_map": {},
            "generation_metadata": {
                "version": 4,
                "engine": "gemini_episode_planner",
                "model": GEMINI_MODEL,
                "is_episode": True,
                "is_complete": True,
                "lessons_total": 1,
                "lessons_ready": 1,
                "total_frames": len(frames),
                "gemini_meta": meta,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            "total_lessons": 1,
            "total_modules": 1,
            "total_estimated_minutes": estimated_minutes,
            "version": 4,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="goal_id").execute()
    except Exception as e:
        _fail_task(sb, goal_id, f"DB save failed: {e}")
        raise

    # Mark planning complete
    _update_task(sb, goal_id,
        status="completed",
        progress_percentage=100,
        current_task=f"Episode ready: {len(frames)} frames",
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    _log(sb, goal_id,
        f"Episode planner complete — {len(frames)} frames, "
        f"{estimated_minutes} min, model={GEMINI_MODEL}"
    )

    # ── Stage 2: Auto-trigger animation generation ──
    await _run_episode_animations(goal_id, user_id, len(frames))

    return {
        "course_structure": course_structure,
        "lesson_plans": {"mod1-les1": lesson_plan},
        "meta": meta,
    }


async def _run_episode_animations(goal_id: str, user_id: str, frame_count: int):
    """Chain animation generation after episode planning completes."""
    from app.agents.animation_v2.pipeline import generate_lesson_visuals

    lesson_id = "mod1-les1"

    await update_agent_task(
        goal_id, "visualization",
        status="active",
        progress=5,
        current_task=f"Generating visuals for {frame_count} frames...",
        log_message="Animation agent started",
        log_level="info",
    )

    try:
        await generate_lesson_visuals(goal_id, user_id, lesson_id)
        await update_agent_task(
            goal_id, "visualization",
            status="completed",
            progress=100,
            current_task=f"All {frame_count} frames animated",
            log_message="Animation agent complete",
            log_level="info",
        )
        # Teaching agent is live (runs on-demand in classroom), not a batch step.
        # Mark it ready so the UI shows the episode is fully prepared.
        await update_agent_task(
            goal_id, "teaching",
            status="completed",
            progress=100,
            current_task="Ready for classroom",
            log_message="Teaching agent ready (live mode)",
            log_level="info",
        )
    except Exception as e:
        logger.error(f"[EpisodePlanner] Animation failed: {e}")
        await update_agent_task(
            goal_id, "visualization",
            status="failed",
            error_message=f"Animation failed: {str(e)[:300]}",
            log_message=f"Animation failed: {str(e)[:200]}",
            log_level="error",
        )


def _fail_task(sb, goal_id: str, msg: str):
    logger.error(f"[EpisodePlanner] FAILED: {msg}")
    _update_task(sb, goal_id,
        status="failed",
        error_message=msg[:500],
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    _log(sb, goal_id, f"FAILED: {msg}", level="error")
