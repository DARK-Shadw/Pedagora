"""Per-step narration generator — tuned to validated animation content.

PIPELINE STAGE 3, narration sub-step (see docs/architecture-flow.svg)

After GSAP code is generated AND validated by Playwright, this module calls
Gemini to produce 3b1b-style narration for each animation step. The narration is:
  - Tuned to the actual generated animation (validated GSAP labels + descriptions)
  - Timed to fill ~85% of each step's animation gap
  - Written in 3Blue1Brown voice (short sentences, concrete nouns)

Browser path: runs AFTER validation passes, receives animation_context with
validated GSAP labels. Runs in parallel with the visual critic (~0 extra time).
Manim path: runs in parallel with the longer render (no animation context).
The result is stored back into course_plans so the Teacher Agent picks it up
directly, eliminating the runtime Groq fallback for narration expansion.
"""

import json
import logging
import re

from app.agents.animation_v2.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

NARRATION_SYSTEM = """\
You are a 3Blue1Brown-style narrator for an educational animation platform.
You write the exact words a teacher will speak while the animation plays.
The speech is synthesized by a TTS engine, so write for the ear, not the eye.

VOICE RULES (non-negotiable):
- Average sentence: 10-14 words. Hard cap: 16 words.
- Use SPECIFIC concrete nouns: "this array", "the middle element", "index 4".
- NEVER say "the visualization", "the animation", "the thing", "this concept".
- Mark deliberate pauses with "..." — TTS honors them as 300ms silence.
- Ask a rhetorical question at least once per 4 steps.
- NO LaTeX, NO underscores, NO subscripts, NO code syntax.
  Write "log n" not "log_n". Write "n squared" not "n^2".
  Write "x sub i" not "x_i". Write "the fraction a over b" not "a/b".
- BANNED openers: "Look at", "Notice how", "In this video", "Let us",
  "Today we", "It is important to note", "As you can see".
- BANNED filler: "kind of like", "really cool", "super cool", "amazing thing",
  "let me explain", "as we can see"."""

NARRATION_PROMPT = """\
Write narration for each step of this animation. The student SEES the animation
while hearing your words — refer to what's visible on screen.

FRAME: {frame_id}
TYPE: {visual_type}
WHAT'S ON SCREEN: {description}
{animation_context_section}
STEPS (write narration for each):
{steps_section}

DURATION TARGETS (each step's narration must fill approximately this time):
{duration_targets}

At ~150 words per minute, that's ~2.5 words per second.
A 10-second target means ~25 words. A 5-second target means ~12 words.

Return a JSON array with EXACTLY {step_count} strings, one per step, in order.
Put the JSON array inside the `code` field of your response.
Example: ["First step narration here.", "Second step narration.", ...]
"""

FILL_RATIO = 0.85
MIN_STEP_DURATION = 3.0
MAX_STEP_DURATION = 20.0


def _compute_duration_targets(
    steps: list[dict], estimated_seconds: float,
) -> list[float]:
    """Compute per-step speech duration targets from anim_time gaps.

    Uses anim_time differences between consecutive steps. For the last step,
    uses duration_seconds or the remaining time. Targets 85% fill to leave
    breathing room for animation transitions.
    """
    if not steps:
        return []

    targets: list[float] = []
    for i, step in enumerate(steps):
        current_time = step.get("anim_time", 0.0)
        if i + 1 < len(steps):
            next_time = steps[i + 1].get("anim_time", current_time)
            gap = max(next_time - current_time, MIN_STEP_DURATION)
        else:
            gap = step.get("duration_seconds", 8.0)

        target = round(gap * FILL_RATIO, 1)
        targets.append(max(MIN_STEP_DURATION, min(target, MAX_STEP_DURATION)))

    return targets


def _build_animation_context_section(ctx: dict | None) -> str:
    """Format the optional animation context block for the narration prompt."""
    if not ctx:
        return ""

    lines = [
        "\nVALIDATED ANIMATION (this animation passed runtime checks — these are the "
        "actual visual states the student sees):"
    ]

    labels = ctx.get("validated_labels") or []
    if labels:
        lines.append("  Timeline labels (GSAP): " + ", ".join(f"'{l}'" for l in labels))

    duration = ctx.get("duration")
    if duration:
        lines.append(f"  Total timeline duration: {duration:.1f}s")

    lines.append(
        "Your narration plays in sync with these labels. Describe what the student "
        "SEES at each state transition — not abstract concepts.\n"
    )

    return "\n".join(lines)


async def generate_frame_narration(
    gemini: GeminiClient,
    frame: dict,
    animation_context: dict | None = None,
) -> list[str] | None:
    """Generate 3b1b-style narration for each step of a frame.

    Args:
        animation_context: Optional dict from the runtime validator with:
            - validated_labels: list[str] — actual GSAP labels found in timeline
            - duration: float — total animation timeline duration
        When provided, narration is tuned to the actual generated animation
        rather than just storyboard descriptions.

    Returns a list of narration strings (one per step), or None if generation
    fails. Caller should fall back to existing narration_spoken from the
    Episode Planner.
    """
    steps = frame.get("steps", [])
    if not steps:
        return None

    frame_id = frame.get("frame_id", "unknown")
    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)[:400]

    visual_type = frame.get("visual_type", "animation")
    estimated_seconds = frame.get("estimated_seconds", 30)

    step_lines = []
    for i, s in enumerate(steps):
        label = s.get("label", s.get("step_id", f"step-{i}"))
        desc = s.get("description", "")
        step_lines.append(f"  {i + 1}. Step '{label}': {desc}")
    steps_section = "\n".join(step_lines)

    targets = _compute_duration_targets(steps, estimated_seconds)
    duration_lines = []
    for i, (s, target) in enumerate(zip(steps, targets)):
        label = s.get("label", s.get("step_id", f"step-{i}"))
        words = round(target * 2.5)
        duration_lines.append(f"  Step '{label}': ~{target}s (~{words} words)")
    duration_targets = "\n".join(duration_lines)

    animation_context_section = _build_animation_context_section(animation_context)

    prompt = NARRATION_PROMPT.format(
        frame_id=frame_id,
        visual_type=visual_type,
        description=description[:500],
        animation_context_section=animation_context_section,
        steps_section=steps_section,
        duration_targets=duration_targets,
        step_count=len(steps),
    )

    try:
        raw_code, meta = await gemini.generate_code(
            prompt=prompt,
            system_prompt=NARRATION_SYSTEM,
            temperature=0.4,
            max_key_rotations=1,
        )
        elapsed = meta.get("elapsed_seconds", 0)
        logger.info(
            f"[Narration] {frame_id}: generated in {elapsed:.1f}s "
            f"(key#{meta.get('key_index')})"
        )
    except Exception as e:
        logger.warning(f"[Narration] {frame_id}: Gemini call failed: {e}")
        return None

    return _parse_narration_response(raw_code, frame_id, len(steps))


def _parse_narration_response(
    raw: str, frame_id: str, expected_count: int,
) -> list[str] | None:
    """Parse the Gemini response into a list of narration strings.

    The response comes through GeminiClient.generate_code which extracts the
    `code` field. The content is a JSON array stringified into that field.
    """
    raw = (raw or "").strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    # Try direct JSON parse
    narrations = None
    try:
        narrations = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting an array from within the text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                narrations = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if narrations is None:
        logger.warning(
            f"[Narration] {frame_id}: JSON parse failed, raw={raw[:200]!r}"
        )
        return None

    if not isinstance(narrations, list):
        logger.warning(
            f"[Narration] {frame_id}: expected list, "
            f"got {type(narrations).__name__}"
        )
        return None

    if len(narrations) != expected_count:
        logger.warning(
            f"[Narration] {frame_id}: count mismatch "
            f"(got {len(narrations)}, expected {expected_count})"
        )
        if len(narrations) < expected_count:
            return None
        narrations = narrations[:expected_count]

    result: list[str] = []
    for i, n in enumerate(narrations):
        text = str(n).strip()
        if not text or len(text) < 10:
            logger.warning(
                f"[Narration] {frame_id}: step {i} too short ({len(text)} chars)"
            )
            return None
        result.append(text)

    avg_len = sum(len(t) for t in result) // max(1, len(result))
    logger.info(
        f"[Narration] {frame_id}: OK — {len(result)} steps, "
        f"avg {avg_len} chars/step"
    )
    return result
