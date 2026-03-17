"""5-stage research pipeline v2.

Stage 1: DECOMPOSE — break goal into topic groups with content_needs
Stage 2: SEARCH   — deterministic search across all APIs, dedup
Stage 3: EXTRACT  — LLM-powered deep extraction per topic
Stage 4: SYNTHESIZE — cross-reference all extractions into learning plan
Stage 5: GAP_FILL — conditional targeted search for critical gaps
"""

import asyncio
import logging
import traceback

from app.agents.decompose import run_decompose
from app.agents.search import run_search
from app.agents.extract import run_extract_for_topic
from app.agents.synthesize import run_synthesize
from app.agents.gap_fill import run_gap_fill
from app.config import get_settings
from app.models.domain import TopicResearchResult, SynthesisGap
from app.services.agent_task import (
    fetch_onboarding_data,
    update_agent_task,
    save_research_sources,
    save_research_results,
    cleanup_previous_research,
)

logger = logging.getLogger(__name__)

AGENT_TYPE = "research"


async def run_research_pipeline(goal_id: str, user_id: str) -> None:
    """Full 5-stage research pipeline v2."""
    try:
        # Dynamic inter-topic delay based on extract model provider
        settings = get_settings()
        if settings.effective_extract_model.startswith("google-gla:"):
            inter_topic_delay = 15  # Gemini: 15 RPM
        else:
            inter_topic_delay = 3  # Groq/Pollinations: generous RPM

        # Mark as active
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="active",
            progress=0,
            current_task="Starting research pipeline v2...",
            log_message="Research pipeline v2 started",
            log_level="system",
        )

        # Clean up any previous research data (retry scenario)
        await cleanup_previous_research(goal_id)

        # Fetch onboarding data
        onboarding_data = await fetch_onboarding_data(goal_id, user_id)
        goal_title = onboarding_data["goal"].get("title", "Unknown goal")

        # ===== STAGE 1: DECOMPOSE (0-8%) =====
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=2,
            current_task="Analyzing your learning goal...",
            focus="decompose",
            log_message=f"Decomposing goal: {goal_title}",
        )

        topic_tree = await run_decompose(onboarding_data)

        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=8,
            current_task=f"Identified {len(topic_tree.topic_groups)} topic groups",
            log_message=f"Decomposition complete: {len(topic_tree.topic_groups)} topics with content needs",
            log_level="success",
        )

        # ===== STAGE 2: SEARCH (8-25%) =====
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=10,
            current_task="Searching across web, academic, and code sources...",
            focus="search",
            log_message="Starting multi-source search (no LLM, deterministic)",
        )

        raw_results = await run_search(topic_tree, goal_id=goal_id, user_id=user_id)

        total_raw = sum(len(v) for v in raw_results.values())
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=25,
            current_task=f"Found {total_raw} unique sources across all topics",
            log_message=f"Search complete: {total_raw} deduplicated results",
            log_level="success",
        )

        # ===== STAGE 3: EXTRACT (25-80%) =====
        topic_results: list[TopicResearchResult] = []
        total_topics = len(topic_tree.topic_groups)
        education_level = onboarding_data.get("profile", {}).get(
            "education_level", "self_learner"
        )

        for i, topic_group in enumerate(topic_tree.topic_groups):
            progress_start = 25 + (55 * i / total_topics)
            progress_end = 25 + (55 * (i + 1) / total_topics)

            await update_agent_task(
                goal_id,
                AGENT_TYPE,
                progress=round(progress_start, 1),
                current_task=f"Deep extraction: {topic_group.name}",
                focus=topic_group.name,
                log_message=f"Extracting topic {i + 1}/{total_topics}: {topic_group.name}",
            )

            topic_raw = raw_results.get(topic_group.name, [])

            try:
                result = await run_extract_for_topic(
                    topic_group=topic_group,
                    raw_results=topic_raw,
                    goal_title=goal_title,
                    education_level=education_level,
                )
                topic_results.append(result)

                # Save sources for this topic immediately
                sources_dicts = [s.model_dump() for s in result.sources]
                await save_research_sources(goal_id, user_id, sources_dicts)

                await update_agent_task(
                    goal_id,
                    AGENT_TYPE,
                    progress=round(progress_end, 1),
                    log_message=(
                        f"Extracted {len(result.sources)} sources for {topic_group.name} "
                        f"(formulas: {len(result.topic_formulas)}, "
                        f"codebases: {len(result.codebase_references)})"
                    ),
                    log_level="success",
                )
            except Exception as e:
                logger.error(f"Extraction failed for topic {topic_group.name}: {e}")
                await update_agent_task(
                    goal_id,
                    AGENT_TYPE,
                    progress=round(progress_end, 1),
                    log_message=f"Extraction partially failed for {topic_group.name}: {str(e)[:100]}",
                    log_level="error",
                )
                # Continue with next topic — don't kill the pipeline

            # Pace requests to stay within LLM rate limits
            if i < total_topics - 1:
                await asyncio.sleep(inter_topic_delay)

        # ===== STAGE 4: SYNTHESIZE (80-92%) =====
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=82,
            current_task="Synthesizing research findings with teaching data...",
            focus="synthesize",
            log_message="Starting deep synthesis of all research findings",
        )

        synthesis = await run_synthesize(topic_results, onboarding_data)

        # Programmatic gap severity override based on actual data
        for gap in synthesis.gaps_identified:
            topic_tg = next((tg for tg in topic_tree.topic_groups if tg.name == gap.topic), None)
            topic_result = next((tr for tr in topic_results if tr.topic_group == gap.topic), None)
            if topic_tg and topic_result:
                needs = topic_tg.content_needs
                has_formulas = len(topic_result.topic_formulas) > 0
                has_code = any(
                    s.extracted_content and len(s.extracted_content.code_snippets) > 0
                    for s in topic_result.sources if s.extracted_content
                )
                if needs.needs_formulas and not has_formulas:
                    gap.severity = "critical"
                    gap.missing_content_type = "formulas"
                if needs.needs_code_examples and not has_code:
                    gap.severity = "critical"
                    gap.missing_content_type = "code_examples"

        # Programmatic fallback: if synthesis returned too few cross-topic formulas,
        # collect top formulas from individual topic results
        if len(synthesis.cross_topic_formulas) < 3:
            all_topic_formulas = []
            for tr in topic_results:
                for f in tr.topic_formulas:
                    all_topic_formulas.append(f)
            # Deduplicate
            seen = set()
            unique = []
            for f in all_topic_formulas:
                key = f.plain_text.strip().lower().replace(" ", "")
                if key not in seen:
                    seen.add(key)
                    unique.append(f)
            # Take top 10 (they're already from the best sources)
            synthesis.cross_topic_formulas = unique[:10]
            logger.info(
                f"Cross-topic formula fallback: collected {len(synthesis.cross_topic_formulas)} "
                f"formulas from topic results"
            )

        # Add gaps for topics the synthesis missed entirely
        for tg in topic_tree.topic_groups:
            topic_result = next((tr for tr in topic_results if tr.topic_group == tg.name), None)
            if not topic_result or len(topic_result.sources) < 2:
                existing_gap = next((g for g in synthesis.gaps_identified if g.topic == tg.name), None)
                if not existing_gap:
                    synthesis.gaps_identified.append(SynthesisGap(
                        topic=tg.name, description="Fewer than 2 sources found",
                        severity="critical", missing_content_type="general",
                    ))

        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=92,
            log_message=(
                f"Synthesis complete. Gaps found: {len(synthesis.gaps_identified)} "
                f"(critical: {sum(1 for g in synthesis.gaps_identified if g.severity == 'critical')})"
            ),
            log_level="success",
        )

        # ===== STAGE 5: GAP_FILL (92-98%) — conditional =====
        critical_gaps = [
            g for g in synthesis.gaps_identified if g.severity == "critical"
        ]

        if critical_gaps:
            await update_agent_task(
                goal_id,
                AGENT_TYPE,
                progress=93,
                current_task=f"Filling {len(critical_gaps)} critical knowledge gaps...",
                focus="gap_fill",
                log_message=f"Gap-filling {len(critical_gaps)} critical gaps: {[g.topic for g in critical_gaps[:3]]}",
            )

            gap_results = await run_gap_fill(
                critical_gaps, topic_tree, topic_results, onboarding_data
            )

            if gap_results:
                # Save gap-fill sources
                for gr in gap_results:
                    sources_dicts = [s.model_dump() for s in gr.sources]
                    await save_research_sources(goal_id, user_id, sources_dicts)
                topic_results.extend(gap_results)

                # Re-synthesize with new data
                await update_agent_task(
                    goal_id,
                    AGENT_TYPE,
                    progress=97,
                    current_task="Re-synthesizing with gap-filled data...",
                    log_message=f"Re-synthesizing with {len(gap_results)} gap-fill results",
                )
                synthesis = await run_synthesize(topic_results, onboarding_data)

            await update_agent_task(
                goal_id,
                AGENT_TYPE,
                progress=98,
                log_message=f"Gap-fill complete. Added {sum(len(gr.sources) for gr in gap_results)} sources.",
                log_level="success",
            )
        else:
            await update_agent_task(
                goal_id,
                AGENT_TYPE,
                progress=98,
                log_message="No critical gaps — skipping gap-fill stage",
                log_level="info",
            )

        # ===== SAVE FINAL RESULTS (98-100%) =====
        topic_tree_dict = topic_tree.model_dump()
        synthesis_dict = synthesis.model_dump()
        total_sources = sum(len(tr.sources) for tr in topic_results)

        await save_research_results(
            goal_id, user_id, topic_tree_dict, synthesis_dict, total_sources
        )

        # ===== COMPLETE (100%) =====
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="completed",
            progress=100,
            current_task="Research complete!",
            focus=None,
            log_message=(
                f"Research pipeline v2 completed. {total_sources} sources across "
                f"{len(topic_results)} topics. "
                f"Formulas: {sum(len(tr.topic_formulas) for tr in topic_results)}, "
                f"Codebases: {sum(len(tr.codebase_references) for tr in topic_results)}, "
                f"Exercises: {sum(len(tr.coding_exercises) for tr in topic_results)}"
            ),
            log_level="success",
        )

    except Exception as e:
        logger.error(f"Research pipeline failed: {traceback.format_exc()}")
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="failed",
            current_task="Pipeline failed",
            error_message=str(e)[:500],
            log_message=f"Pipeline error: {str(e)[:200]}",
            log_level="error",
        )
