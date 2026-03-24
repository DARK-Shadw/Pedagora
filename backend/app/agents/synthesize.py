from pydantic_ai import Agent

from app.agents.models import create_model
from app.agents.prompts import SYNTHESIZE_SYSTEM_PROMPT
from app.agents.retry import run_with_retry
from app.config import get_settings
from app.models.domain import ResearchSynthesis, TopicResearchResult


async def run_synthesize(
    topic_results: list[TopicResearchResult],
    onboarding_data: dict,
) -> ResearchSynthesis:
    """Stage 4: Synthesize all topic research into a cohesive learning plan with teaching data."""
    goal = onboarding_data["goal"]
    preferences = onboarding_data.get("preferences", {})
    profile = onboarding_data.get("profile", {})

    # Build rich research data summary for the prompt
    research_lines = []
    total_sources = 0
    for tr in topic_results:
        research_lines.append(f"\n## Topic: {tr.topic_group}")
        research_lines.append(f"Notes: {tr.notes}")
        research_lines.append(f"Sources found: {len(tr.sources)}")

        for s in tr.sources:
            research_lines.append(
                f"  - [{s.source_type}] {s.title} (relevance: {s.relevance_score}, "
                f"credibility: {s.credibility_score})"
            )
            if s.key_concepts:
                research_lines.append(f"    Concepts: {', '.join(s.key_concepts[:8])}")
            # Include extracted content summaries
            if s.extracted_content and s.extracted_content.detailed_summary:
                summary = s.extracted_content.detailed_summary[:300]
                research_lines.append(f"    Summary: {summary}")
            if s.extracted_content and s.extracted_content.misconceptions:
                misconceptions = [m.misconception for m in s.extracted_content.misconceptions[:3]]
                research_lines.append(f"    Misconceptions: {'; '.join(misconceptions)}")
            if s.extracted_content and s.extracted_content.analogies:
                analogies = [a.analogy[:100] for a in s.extracted_content.analogies[:2]]
                research_lines.append(f"    Analogies: {'; '.join(analogies)}")

        # Include aggregated data counts
        if tr.topic_formulas:
            formula_names = [f.description[:60] for f in tr.topic_formulas[:5]]
            research_lines.append(f"  Formulas ({len(tr.topic_formulas)}): {'; '.join(formula_names)}")

        if tr.topic_numerical_data:
            research_lines.append(f"  Numerical examples: {len(tr.topic_numerical_data)}")

        if tr.codebase_references:
            repos = [f"{r.repo_name} ({r.stars} stars, suitability: {r.suitability_score})"
                     for r in tr.codebase_references]
            research_lines.append(f"  Codebases: {'; '.join(repos)}")

        if tr.coding_exercises:
            exercises = [f"{e.title} ({e.difficulty})" for e in tr.coding_exercises[:3]]
            research_lines.append(f"  Exercises: {'; '.join(exercises)}")

        # Explicit content status so the LLM can't miss what exists
        code_count = sum(
            len(s.extracted_content.code_snippets)
            for s in tr.sources if s.extracted_content
        )
        research_lines.append(
            f"  >>> CONTENT STATUS: formulas={len(tr.topic_formulas)}, "
            f"code_snippets={code_count}, exercises={len(tr.coding_exercises)}, "
            f"codebases={len(tr.codebase_references)}, sources={len(tr.sources)}"
        )

        total_sources += len(tr.sources)

    system_prompt = SYNTHESIZE_SYSTEM_PROMPT.format(
        goal_title=goal.get("title", ""),
        end_goal=goal.get("end_goal", "Not specified"),
        education_level=profile.get("education_level", "self_learner"),
        content_depth=preferences.get("content_depth", "intermediate"),
        research_data="\n".join(research_lines),
    )

    settings = get_settings()
    agent = Agent(
        create_model(settings.synthesize_model),
        system_prompt=system_prompt,
        output_type=ResearchSynthesis,
    )

    async def _run():
        result = await agent.run(
            f"Synthesize the research findings for the learning goal: {goal.get('title', '')}. "
            f"Total sources found: {total_sources}."
        )
        return result.output

    return await run_with_retry(_run)
