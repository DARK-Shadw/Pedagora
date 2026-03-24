"""Adaptive research effort profiles.

Single source of truth for effort tiers — light, standard, deep.
Controls how many topics, sources, and LLM calls the pipeline uses.
"""

from typing import Literal

EffortTier = Literal["light", "standard", "deep"]

EFFORT_PROFILES: dict[str, dict] = {
    "light": {
        "topics_min": 2,
        "topics_max": 4,
        "queries_per_topic_min": 1,
        "queries_per_topic_max": 2,
        "max_sources_per_topic": 3,
        "max_codebase_analyses": 0,
        "gap_fill_enabled": False,
        "max_gap_topics": 0,
        "synthesize_formula_target": 3,
    },
    "standard": {
        "topics_min": 4,
        "topics_max": 7,
        "queries_per_topic_min": 2,
        "queries_per_topic_max": 3,
        "max_sources_per_topic": 5,
        "max_codebase_analyses": 2,
        "gap_fill_enabled": True,
        "max_gap_topics": 3,
        "synthesize_formula_target": 5,
    },
    "deep": {
        "topics_min": 6,
        "topics_max": 10,
        "queries_per_topic_min": 3,
        "queries_per_topic_max": 4,
        "max_sources_per_topic": 8,
        "max_codebase_analyses": 3,
        "gap_fill_enabled": True,
        "max_gap_topics": 5,
        "synthesize_formula_target": 10,
    },
}

# Maps common LLM hallucinations / synonyms to valid tier names
_TIER_ALIASES: dict[str, EffortTier] = {
    # light aliases
    "light": "light",
    "simple": "light",
    "basic": "light",
    "easy": "light",
    "quick": "light",
    "brief": "light",
    "minimal": "light",
    "introductory": "light",
    "beginner": "light",
    "shallow": "light",
    "overview": "light",
    # standard aliases
    "standard": "standard",
    "medium": "standard",
    "moderate": "standard",
    "normal": "standard",
    "default": "standard",
    "intermediate": "standard",
    "regular": "standard",
    "balanced": "standard",
    # deep aliases
    "deep": "deep",
    "advanced": "deep",
    "comprehensive": "deep",
    "thorough": "deep",
    "extensive": "deep",
    "detailed": "deep",
    "intensive": "deep",
    "expert": "deep",
    "complex": "deep",
    "heavy": "deep",
}


def validate_effort_tier(raw: str) -> EffortTier:
    """Normalize an LLM-returned tier string to a valid EffortTier.

    Falls back to "standard" for any unrecognized value.
    """
    normalized = raw.strip().lower()
    return _TIER_ALIASES.get(normalized, "standard")


def get_effort_profile(tier: str) -> dict:
    """Return the effort profile dict for a tier. Defaults to standard."""
    return EFFORT_PROFILES.get(tier, EFFORT_PROFILES["standard"])
