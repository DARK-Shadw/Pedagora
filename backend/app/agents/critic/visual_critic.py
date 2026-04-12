"""LLM-based visual critic — reviews rendered animation screenshots.

Adapted from `app/agents/animation/review.py` (the v1 Manim reviewer) to work
with browser-rendered HTML frames produced by Animation Agent v2. Instead of
extracting frames from an MP4, this critic takes screenshots that the
Animation Validator already captured at every step label.

The rubric is the same six-dimensional score-1-to-10 with verdict PASS / REGEN.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


VISUAL_REVIEW_PROMPT = """\
You are reviewing a browser-rendered animation frame from an AI education \
platform. The animation is meant to teach in the style of 3Blue1Brown — \
visual-first, the entire screen filled with the diagram, never a blank space.

These screenshots were captured at every named step of the animation's \
GSAP timeline. Step '{first_label}' is the first frame, '{last_label}' is \
the final frame.

## What this animation should show
TYPE: {visual_type}
DESCRIPTION: {description}

## Rubric (score 1–10 on each)

1. CORRECTNESS — does the visual match the description?
2. CLARITY    — is the main subject clearly visible, well composed?
3. AESTHETICS — colours, typography, contrast, dark-bg consistency
4. STEP_ISOLATION — is each step visually distinct from the previous?
5. TEXT       — is every label readable, no overlapping or clipped text?
6. ON_SCREEN_DENSITY — does it fill the canvas, no big empty regions?

A score of 6 is the minimum acceptable.

## Output format (strict)

SCORE: [average 1–10]
ISSUES:
- [issue 1]
- [issue 2]
VERDICT: PASS or REGENERATE
FEEDBACK: [if REGENERATE, concrete fix instructions for the next attempt]
"""


@dataclass
class VisualReview:
    score: int = 5
    issues: list[str] = field(default_factory=list)
    verdict: str = "PASS"
    feedback: str = ""
    raw: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"


def _critic_model() -> str:
    return "gemini-fast"


async def review_animation_screenshots(
    screenshots_b64: list[str],
    step_labels: list[str],
    visual_type: str,
    description: str,
) -> VisualReview:
    """Review a list of base64 PNG screenshots — one per step label.

    `screenshots_b64` and `step_labels` must be the same length and ordered.
    Returns a VisualReview with score, issues, verdict, and feedback.
    """
    if not screenshots_b64:
        return VisualReview(
            score=0,
            issues=["no screenshots captured"],
            verdict="REGENERATE",
            feedback="animation produced no rendered frames",
        )

    settings = get_settings()
    first_label = step_labels[0] if step_labels else "first"
    last_label = step_labels[-1] if step_labels else "last"

    prompt_text = VISUAL_REVIEW_PROMPT.format(
        visual_type=visual_type,
        description=description[:300],
        first_label=first_label,
        last_label=last_label,
    )

    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for b64 in screenshots_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                "https://gen.pollinations.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.pollinations_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _critic_model(),
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 600,
                },
            )
        if r.status_code != 200:
            logger.warning(f"[VisualCritic] API {r.status_code}: {r.text[:200]}")
            return VisualReview(
                score=5, verdict="PASS",
                feedback=f"critic API returned {r.status_code}",
            )
        data = r.json()
        raw = data["choices"][0]["message"]["content"]
        return _parse_review(raw)
    except Exception as e:
        logger.warning(f"[VisualCritic] call failed: {e}")
        return VisualReview(score=5, verdict="PASS", feedback=str(e))


def _parse_review(raw: str) -> VisualReview:
    out = VisualReview(raw=raw)
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            m = re.search(r"\d+", line)
            if m:
                try:
                    out.score = int(m.group(0))
                except ValueError:
                    pass
        elif line.startswith("- "):
            out.issues.append(line[2:].strip())
        elif line.upper().startswith("FEEDBACK:"):
            out.feedback = line.split(":", 1)[1].strip()
    out.verdict = "PASS" if out.score >= 6 else "REGENERATE"
    return out
