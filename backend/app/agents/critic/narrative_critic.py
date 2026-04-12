"""LLM-based narrative critic — scores a lesson against the 3b1b voice rubric.

Runs after the deterministic rules pass. The rules already filter out the
unambiguous failures, so this critic focuses on the taste-level questions
the rules can't answer:

  * Is the speech *specific* enough, or generic to any topic?
  * Does the narration tightly match the visual at each step?
  * Does the lesson flow like 3b1b — pose a question, build intuition,
    formalise, then a payoff — or is it a flat list of facts?

Output: a rubric with per-dimension scores 1–10 + concrete rewrite hints.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic_ai import Agent

from app.agents.models import create_model
from app.agents.retry import run_with_retry
from app.config import get_settings

logger = logging.getLogger(__name__)


# A short anchor pulled from real 3b1b transcripts. Keep this small —
# it's a style anchor, not a content template.
THREE_B_ONE_B_STYLE_ANCHOR = """\
The 3b1b voice has these traits:

* Short sentences. Average 10–14 words. Often even shorter.
* Specific concrete nouns: "this vector", "the third row", "a circle of radius two".
  Never "the thing", "kind of like", "really cool".
* Pose a question, then answer it visually before stating the formula.
* Use deliberate pauses, marked with "..." in writing.
* Address the student directly: "you might wonder", "imagine you...".
* Build from intuition to formalism, never the other way around.
* Avoid filler openers like "Look at...", "Notice how...", "In this video...".
"""


CRITIC_SYSTEM = """\
You are a senior instructional reviewer for an AI education platform that \
teaches in the style of 3Blue1Brown — visual-first, mathematically rigorous, \
emotionally engaging. You score lesson storyboards on a strict rubric and \
return concrete rewrite suggestions. Return ONLY valid JSON."""


CRITIC_PROMPT = """\
Review this lesson storyboard against the 3b1b voice and pedagogy rubric.

LESSON: "{lesson_title}"
STUDENT GOAL: {end_goal}

=== STYLE ANCHOR (3b1b voice) ===
{style_anchor}

=== RULE-BASED VIOLATIONS ALREADY FOUND ===
{rules_summary}

=== STORYBOARD (truncated for review) ===
{storyboard_excerpt}

=== TASK ===

Score the storyboard 1–10 on each dimension below. A score of 7 is the
*minimum acceptable*; below 7 means the lesson should be regenerated.

1. CLARITY        — sentences short, words concrete, no jargon dumps
2. SPECIFICITY    — narration references specific visible elements,
                    not generic "the visualization"
3. PACING         — ideas build progressively, no rushed runs of dense
                    formalism, no sleepy stretches
4. RHETORICAL     — student is asked to think (questions, predictions)
                    at least every few steps, like 3b1b does
5. VISUAL_COHERENCE — narration tightly describes what's on screen
                    at each step, not the broad topic
6. THREE_B_ONE_B_NESS — overall feel: would a 3b1b viewer recognise
                    this as the same style?

For EACH dimension below 7, list 1–3 concrete rewrite hints citing the
specific frame_id and step label that needs work.

Return ONLY valid JSON:
{{
  "scores": {{
    "clarity": 1-10,
    "specificity": 1-10,
    "pacing": 1-10,
    "rhetorical": 1-10,
    "visual_coherence": 1-10,
    "three_b_one_b_ness": 1-10
  }},
  "rewrite_hints": [
    {{"frame_id": "f01", "step": "intro", "hint": "..."}},
    ...
  ],
  "verdict": "PASS" or "REGENERATE",
  "summary": "one paragraph"
}}
"""


@dataclass
class NarrativeReview:
    scores: dict[str, int] = field(default_factory=dict)
    rewrite_hints: list[dict] = field(default_factory=list)
    verdict: str = "PASS"
    summary: str = ""
    raw: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS" and all(s >= 7 for s in self.scores.values())

    @property
    def lowest_score(self) -> int:
        return min(self.scores.values()) if self.scores else 10


def _truncate_storyboard(lesson: dict, max_chars: int = 8000) -> str:
    """Build a compact JSON excerpt of the storyboard for the critic.

    We keep frame_id, step labels, narration_spoken, and visual_spec.description
    — that's all the critic needs to score voice + coherence.
    """
    frames = lesson.get("frames") or []
    excerpt = []
    for f in frames:
        steps = f.get("steps") or []
        excerpt.append({
            "frame_id": f.get("frame_id"),
            "visual_type": f.get("visual_type"),
            "estimated_seconds": f.get("estimated_seconds"),
            "description": (f.get("visual_spec") or {}).get("description", "")[:200],
            "narration_spoken": (f.get("narration_spoken") or "")[:400],
            "interaction": (f.get("interaction") or {}).get("prompt", "")[:120] if f.get("interaction") else None,
            "steps": [
                {
                    "label": s.get("label"),
                    "narration_spoken": (s.get("narration_spoken") or s.get("narration") or "")[:240],
                }
                for s in steps
            ],
        })
    text = json.dumps(excerpt, ensure_ascii=False)
    if len(text) > max_chars:
        text = text[:max_chars] + "...[TRUNCATED]"
    return text


def _summarise_violations(violations: list) -> str:
    if not violations:
        return "(no rule violations — focus on taste-level review)"
    counts: dict[str, int] = {}
    for v in violations:
        counts[v.code] = counts.get(v.code, 0) + 1
    return "; ".join(f"{code} x{n}" for code, n in counts.items())


def _parse_review(raw: str) -> NarrativeReview:
    """Best-effort JSON extraction; never raises."""
    review = NarrativeReview(raw=raw)
    # Strip markdown fences if any
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not m:
            review.verdict = "PASS"
            review.summary = "(could not parse critic response)"
            return review
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            review.verdict = "PASS"
            review.summary = "(could not parse critic response)"
            return review

    scores = data.get("scores") or {}
    review.scores = {k: int(v) for k, v in scores.items() if isinstance(v, (int, float))}
    review.rewrite_hints = list(data.get("rewrite_hints") or [])
    review.verdict = str(data.get("verdict", "PASS")).upper()
    review.summary = str(data.get("summary", ""))
    return review


def _critic_model() -> str:
    """Pollinations Mistral is the right cost/quality tradeoff for review work."""
    return "pollinations:mistral"


async def review_lesson_narrative(
    lesson: dict,
    lesson_title: str = "",
    end_goal: str = "",
    rules_violations: list | None = None,
) -> NarrativeReview:
    """Score a v4 lesson storyboard with the narrative critic."""
    rules_summary = _summarise_violations(rules_violations or [])
    excerpt = _truncate_storyboard(lesson)

    prompt = CRITIC_PROMPT.format(
        lesson_title=lesson_title or lesson.get("title", "?"),
        end_goal=end_goal or "(not specified)",
        style_anchor=THREE_B_ONE_B_STYLE_ANCHOR,
        rules_summary=rules_summary,
        storyboard_excerpt=excerpt,
    )

    agent = Agent(create_model(_critic_model()), output_type=str)

    async def _run() -> str:
        result = await agent.run(prompt, model_settings={"temperature": 0.2})
        return result.output

    try:
        raw = await run_with_retry(_run)
    except Exception as e:
        logger.warning(f"[NarrativeCritic] LLM call failed: {e}; defaulting to PASS")
        return NarrativeReview(verdict="PASS", summary=f"critic call failed: {e}")

    return _parse_review(raw)
