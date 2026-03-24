"""Domain lists, bonus query logic, and content-type classification for search."""

from __future__ import annotations

import re

from app.models.domain import ContentNeeds, SearchQuery

# Matches 4-digit years like 2020, 2023 in a query string
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

CODE_DOMAINS = [
    "github.com",
    "realpython.com",
    "pytorch.org",
    "huggingface.co",
    "kaggle.com",
    "docs.python.org",
    "tensorflow.org",
    "geeksforgeeks.org",
    "developer.mozilla.org",
    "docs.scipy.org",
    "numpy.org",
]

FORMULA_DOMAINS = [
    "arxiv.org",
    "distill.pub",
    "lilianweng.github.io",
    "mathworld.wolfram.com",
    "brilliant.org",
    "en.wikipedia.org",
    "openreview.net",
]

EXCLUDE_DOMAINS = [
    "pinterest.com",
    "quora.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "instagram.com",
    "reddit.com",
]

FAST_MOVING_KEYWORDS = [
    "machine learning",
    "deep learning",
    "neural network",
    "llm",
    "large language model",
    "transformer",
    "diffusion model",
    "generative ai",
    "react",
    "next.js",
    "nextjs",
    "langchain",
    "pytorch",
    "tensorflow",
    "kubernetes",
    "docker",
    "rust",
    "webassembly",
    "stable diffusion",
    "reinforcement learning",
    "computer vision",
    "natural language processing",
    "nlp",
    "rag",
    "retrieval augmented",
    "fine-tuning",
    "lora",
    "qlora",
    "agents",
    "multimodal",
    "vision language model",
]


def is_fast_moving_field(goal_title: str, topic_name: str) -> bool:
    """Keyword match against combined goal+topic text."""
    combined = f"{goal_title} {topic_name}".lower()
    return any(kw in combined for kw in FAST_MOVING_KEYWORDS)


def query_mentions_year(query: str) -> bool:
    """Return True if the query references a specific year (e.g. 'Ho 2020').

    Scholar queries that target a specific paper by year should NOT have
    year_low filtering applied — it would filter out the exact paper.
    """
    return bool(_YEAR_PATTERN.search(query))


def generate_bonus_queries(
    topic_name: str,
    content_needs: ContentNeeds,
    goal_title: str,
) -> list[tuple[SearchQuery, list[str] | None]]:
    """Return 0-2 (SearchQuery, include_domains) tuples based on content_needs flags.

    - needs_code_examples → 1 code-focused web query (no domain lock — let Tavily
      find the best tutorial naturally via a specific query)
    - needs_formulas → 1 formula-focused web query with FORMULA_DOMAINS
    - Neither flag → empty list (non-STEM topics get zero bonus queries)
    """
    bonus: list[tuple[SearchQuery, list[str] | None]] = []

    if content_needs.needs_code_examples:
        # Specific query phrasing works better than domain-locking for code tutorials.
        # Tavily naturally surfaces realpython, pytorch.org, medium tutorials etc.
        query = SearchQuery(
            query=f"{topic_name} python step by step implementation tutorial from scratch",
            search_type="web",
        )
        bonus.append((query, None))

    if content_needs.needs_formulas:
        query = SearchQuery(
            query=f"{topic_name} mathematical formulation equations derivation",
            search_type="web",
        )
        bonus.append((query, FORMULA_DOMAINS))

    return bonus


def get_github_qualifiers(content_needs: ContentNeeds) -> dict:
    """Return GitHub search qualifiers based on content_needs.

    Returns {"min_stars": N, "language": "python"} when needs_working_codebase.
    Returns {"min_stars": 20} when needs_code_examples only.
    Returns {} otherwise.
    """
    if content_needs.needs_working_codebase:
        return {"min_stars": 50, "language": "python"}
    if content_needs.needs_code_examples:
        return {"min_stars": 20}
    return {}
