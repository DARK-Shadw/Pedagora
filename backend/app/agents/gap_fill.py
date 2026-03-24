"""Stage 5: Targeted gap-filling — conditional, max 1 iteration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pydantic_ai import Agent

from app.agents.models import create_model
from app.agents.prompts import GAP_FILL_SEARCH_PROMPT
from app.agents.retry import run_with_retry
from app.agents.search import _execute_search, _normalize_url, SEARCH_DELAY_SECONDS
from app.agents.search_domains import EXCLUDE_DOMAINS, is_fast_moving_field
from app.agents.extract import run_extract_for_topic
from app.config import get_settings
from app.models.domain import (
    SynthesisGap,
    TopicTree,
    TopicGroup,
    TopicResearchResult,
    SearchQuery,
    ContentNeeds,
)

if TYPE_CHECKING:
    from app.agents.model_pool import ModelPool

logger = logging.getLogger(__name__)

MAX_GAP_TOPICS = 3


async def _generate_gap_queries(
    gap: SynthesisGap,
    goal_title: str,
    education_level: str,
    model_pool: "ModelPool | None" = None,
) -> list[SearchQuery]:
    """Use LLM to generate targeted search queries for a gap."""
    settings = get_settings()

    prompt = GAP_FILL_SEARCH_PROMPT.format(
        gap_topic=gap.topic,
        missing_content_type=gap.missing_content_type,
        gap_description=gap.description,
        goal_title=goal_title,
        education_level=education_level,
    )

    if model_pool:
        async def _run_with_model(model_str: str) -> list[SearchQuery]:
            agent = Agent(create_model(model_str), output_type=list[SearchQuery])
            async def _run():
                result = await agent.run(prompt)
                return result.output
            return await run_with_retry(_run)

        try:
            return await model_pool.run_with_pool(_run_with_model)
        except Exception as e:
            logger.warning(f"Gap query generation failed for {gap.topic}: {e}")
    else:
        agent = Agent(create_model(settings.effective_extract_model), output_type=list[SearchQuery])
        async def _run():
            result = await agent.run(prompt)
            return result.output
        try:
            return await run_with_retry(_run)
        except Exception as e:
            logger.warning(f"Gap query generation failed for {gap.topic}: {e}")

    # Fallback: generate basic queries
    return [
        SearchQuery(
            query=f"{gap.topic} {gap.missing_content_type} tutorial",
            search_type="web",
        ),
        SearchQuery(
            query=f"{gap.topic} {gap.missing_content_type} implementation",
            search_type="github" if gap.missing_content_type in ("code_examples", "working_codebase") else "web",
        ),
    ]


async def run_gap_fill(
    gaps: list[SynthesisGap],
    topic_tree: TopicTree,
    existing_results: list[TopicResearchResult],
    onboarding_data: dict,
    max_gap_topics: int = MAX_GAP_TOPICS,
    model_pool: "ModelPool | None" = None,
) -> list[TopicResearchResult]:
    """Run targeted search + extraction for critical gaps.

    Returns new TopicResearchResults for the gap topics.
    """
    goal = onboarding_data["goal"]
    goal_title = goal.get("title", "")
    education_level = onboarding_data.get("profile", {}).get(
        "education_level", "self_learner"
    )

    # Collect all existing URLs for dedup
    existing_urls: set[str] = set()
    for tr in existing_results:
        for s in tr.sources:
            existing_urls.add(_normalize_url(s.url))

    critical_gaps = gaps[:max_gap_topics]
    logger.info(f"Gap-filling {len(critical_gaps)} critical gaps")

    # Build a lookup for existing topic groups
    topic_lookup = {tg.name: tg for tg in topic_tree.topic_groups}

    # Use a lock to protect existing_urls across parallel gap fills
    urls_lock = asyncio.Lock()

    async def _fill_one_gap(gap: SynthesisGap) -> TopicResearchResult | None:
        logger.info(f"Gap-filling: {gap.topic} (missing: {gap.missing_content_type})")

        # Generate targeted queries
        queries = await _generate_gap_queries(
            gap, goal_title, education_level, model_pool=model_pool
        )
        await asyncio.sleep(SEARCH_DELAY_SECONDS)

        # Execute searches with quality gates
        raw_results: list[dict] = []
        fast_moving = is_fast_moving_field(goal_title, gap.topic)
        for sq in queries:
            kwargs: dict = {}
            if sq.search_type == "web":
                kwargs["exclude_domains"] = EXCLUDE_DOMAINS
            elif sq.search_type == "scholar" and fast_moving:
                kwargs["year_low"] = 2022
            results = await _execute_search(sq.query, sq.search_type, "advanced", **kwargs)
            async with urls_lock:
                for r in results:
                    url = r.get("url", "")
                    if url and _normalize_url(url) not in existing_urls:
                        raw_results.append(r)
                        existing_urls.add(_normalize_url(url))
            await asyncio.sleep(SEARCH_DELAY_SECONDS)

        if not raw_results:
            logger.info(f"No new results found for gap: {gap.topic}")
            return None

        # Build a TopicGroup for extraction
        existing_tg = topic_lookup.get(gap.topic)
        if existing_tg:
            topic_group = existing_tg
        else:
            needs = ContentNeeds(priority="high")
            if "formula" in gap.missing_content_type:
                needs.needs_formulas = True
            if "code" in gap.missing_content_type:
                needs.needs_code_examples = True
                needs.needs_working_codebase = True
            if "concept" in gap.missing_content_type:
                needs.needs_conceptual_depth = True
            if "numerical" in gap.missing_content_type:
                needs.needs_numerical_data = True

            topic_group = TopicGroup(
                name=gap.topic,
                description=gap.description,
                importance="Critical gap identified during synthesis",
                search_queries=queries,
                order=0,
                content_needs=needs,
            )

        try:
            result = await run_extract_for_topic(
                topic_group=topic_group,
                raw_results=raw_results,
                goal_title=goal_title,
                education_level=education_level,
                model_pool=model_pool,
            )
            result.notes = f"[GAP-FILL] {result.notes}"
            return result
        except Exception as e:
            logger.warning(f"Gap-fill extraction failed for {gap.topic}: {e}")
            return None

    if model_pool:
        # Parallel gap filling
        parallel_gap_results = await asyncio.gather(
            *[_fill_one_gap(gap) for gap in critical_gaps]
        )
        gap_results: list[TopicResearchResult] = [
            r for r in parallel_gap_results if r is not None
        ]
    else:
        # Sequential fallback
        gap_results: list[TopicResearchResult] = []
        for gap in critical_gaps:
            result = await _fill_one_gap(gap)
            if result:
                gap_results.append(result)
            await asyncio.sleep(5)

    return gap_results
