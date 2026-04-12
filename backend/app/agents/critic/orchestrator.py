"""Class Critic orchestrator — single entrypoint that aggregates all gates.

Pipeline order (cheapest first):
  1. Rules (deterministic, instant) — hard violations block immediately
  2. Narrative critic (Pollinations Mistral) — taste-level voice review
  3. Visual critic (Gemini-fast) — only the visual gate, run elsewhere

The orchestrator merges everything into a CriticReport with `blocking`
(must regenerate) and `advisory` (warn) lists, plus a final `passed` bool.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agents.critic.rules import (
    Violation,
    check_storyboard,
)
from app.agents.critic.narrative_critic import (
    NarrativeReview,
    review_lesson_narrative,
)

logger = logging.getLogger(__name__)


@dataclass
class CriticReport:
    """Aggregated critic output for a lesson."""
    lesson_id: str
    blocking: list[Violation] = field(default_factory=list)
    advisory: list[Violation] = field(default_factory=list)
    narrative: NarrativeReview | None = None

    @property
    def passed(self) -> bool:
        if self.blocking:
            return False
        if self.narrative is not None and not self.narrative.passed:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "lesson_id": self.lesson_id,
            "passed": self.passed,
            "blocking": [
                {"code": v.code, "message": v.message, "location": v.location}
                for v in self.blocking
            ],
            "advisory": [
                {"code": v.code, "message": v.message, "location": v.location}
                for v in self.advisory
            ],
            "narrative": (
                {
                    "scores": self.narrative.scores,
                    "verdict": self.narrative.verdict,
                    "summary": self.narrative.summary,
                    "rewrite_hints": self.narrative.rewrite_hints,
                }
                if self.narrative
                else None
            ),
        }

    def feedback_for_regeneration(self) -> str:
        """Build a single feedback string to inject into the next regen prompt."""
        parts: list[str] = []
        if self.blocking:
            parts.append("BLOCKING ISSUES (must fix):")
            for v in self.blocking[:30]:
                parts.append(f"- [{v.location or '?'}] {v.code}: {v.message}")
        if self.narrative and self.narrative.rewrite_hints:
            parts.append("\nNARRATIVE REWRITE HINTS:")
            for h in self.narrative.rewrite_hints[:20]:
                fid = h.get("frame_id", "?")
                step = h.get("step", "")
                hint = h.get("hint", "")
                parts.append(f"- {fid}.{step}: {hint}")
        return "\n".join(parts)


async def review_lesson(
    lesson: dict,
    lesson_title: str = "",
    end_goal: str = "",
    skip_narrative: bool = False,
) -> CriticReport:
    """Run the rules + narrative gates on a single v4 lesson storyboard.

    Set `skip_narrative=True` to run rules-only (faster, free, no LLM).
    """
    lesson_id = lesson.get("lesson_id", "?")
    report = CriticReport(lesson_id=lesson_id)

    # 1. Rules
    rules_result = check_storyboard(lesson)
    report.blocking.extend(rules_result.hard)
    report.advisory.extend(rules_result.soft)

    # 2. Narrative critic — only if rules passed (avoid wasting tokens
    #    on a lesson that's already going to be regenerated)
    if rules_result.passed and not skip_narrative:
        try:
            report.narrative = await review_lesson_narrative(
                lesson=lesson,
                lesson_title=lesson_title or lesson.get("title", ""),
                end_goal=end_goal,
                rules_violations=rules_result.violations,
            )
        except Exception as e:
            logger.warning(f"[CriticOrchestrator] narrative review failed: {e}")
            report.narrative = None

    return report
