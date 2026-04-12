"""Class Critic — multi-layer quality gate for the visual-first classroom.

Three layers, run in order from cheapest to most expensive:

  1. rules.py            — pure-Python deterministic checks (free, instant)
  2. narrative_critic.py — LLM review of speech + storyboard coherence
  3. visual_critic.py    — LLM review of rendered animation screenshots

Use orchestrator.review_lesson() as the single entry point.
"""

from app.agents.critic.rules import (
    Severity,
    Violation,
    check_speech_voice,
    check_storyboard,
    check_frame_sync_report,
)

__all__ = [
    "Severity",
    "Violation",
    "check_speech_voice",
    "check_storyboard",
    "check_frame_sync_report",
]
