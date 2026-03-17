"""Stage 3: LLM-powered deep extraction per topic."""

import asyncio
import logging
import json

from pydantic_ai import Agent

from app.agents.prompts import (
    EXTRACT_SYSTEM_PROMPT,
    EXTRACT_RANK_PROMPT,
    EXTRACT_CODE_PROMPT,
    SCORE_CALIBRATION_RUBRIC,
)
from app.agents.models import create_model
from app.agents.retry import run_with_retry
from app.config import get_settings
from app.models.domain import (
    TopicGroup,
    TopicResearchResult,
    SourceInfo,
    ExtractedContent,
    CodebaseReference,
    CodingExercise,
    MathFormula,
    NumericalExample,
)
from app.tools.tavily_extract import tavily_extract
from app.tools.github_content import github_fetch_readme, github_fetch_file, github_fetch_tree
from app.tools.httpx_fetch import httpx_fetch_page

logger = logging.getLogger(__name__)

MAX_SOURCES_PER_TOPIC = 6
MAX_CONTENT_LENGTH = 8000  # chars per source for LLM context


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract owner/repo from a GitHub URL."""
    # https://github.com/owner/repo or https://github.com/owner/repo/...
    if "github.com" not in url:
        return None
    parts = url.rstrip("/").split("github.com/")
    if len(parts) < 2:
        return None
    path_parts = parts[1].split("/")
    if len(path_parts) >= 2:
        return path_parts[0], path_parts[1]
    return None


def _format_raw_results(raw_results: list[dict]) -> str:
    """Format raw search results for the ranking prompt."""
    lines = []
    for i, r in enumerate(raw_results, 1):
        line = f"{i}. [{r.get('search_type', 'web')}] {r.get('title', 'Untitled')}"
        line += f"\n   URL: {r.get('url', '')}"
        snippet = r.get("snippet", "")
        if snippet:
            line += f"\n   Snippet: {snippet[:200]}"
        if r.get("stars"):
            line += f"\n   Stars: {r['stars']}"
        if r.get("year"):
            line += f"\n   Year: {r['year']}"
        lines.append(line)
    return "\n\n".join(lines)


async def _rank_urls(
    topic_name: str,
    raw_results: list[dict],
    max_sources: int,
) -> list[str]:
    """Pick the best URLs to extract content from.

    Uses deterministic ranking (search APIs already sort by relevance)
    to conserve LLM calls for the actual extraction.
    """
    # Prioritize: tutorials/articles first, then GitHub, then papers
    type_priority = {"web": 0, "github": 1, "scholar": 2}
    sorted_results = sorted(
        raw_results,
        key=lambda r: type_priority.get(r.get("search_type", "web"), 3),
    )
    return [r["url"] for r in sorted_results[:max_sources] if r.get("url")]


async def _fetch_content(urls: list[str]) -> dict[str, str]:
    """Fetch full content for a list of URLs. Returns {url: content}."""
    url_content: dict[str, str] = {}

    # Separate resource://, GitHub, and web URLs
    web_urls = []
    github_urls = []
    for url in urls:
        if url.startswith("resource://"):
            # Content is already available from search snippet — skip fetch
            continue
        parsed = _parse_github_url(url)
        if parsed:
            github_urls.append((url, parsed))
        else:
            web_urls.append(url)

    # Fetch web pages via Tavily extract
    if web_urls:
        extracted = await tavily_extract(web_urls)
        extracted_urls = {e["url"] for e in extracted if e.get("raw_content")}
        for e in extracted:
            if e.get("raw_content"):
                url_content[e["url"]] = e["raw_content"][:MAX_CONTENT_LENGTH]

        # Fallback to httpx for URLs Tavily couldn't extract
        missing_urls = [u for u in web_urls if u not in extracted_urls]
        for url in missing_urls:
            content = await httpx_fetch_page(url)
            if content:
                url_content[url] = content[:MAX_CONTENT_LENGTH]

    # Fetch GitHub READMEs
    for url, (owner, repo) in github_urls:
        readme = await github_fetch_readme(owner, repo)
        if readme:
            url_content[url] = readme[:MAX_CONTENT_LENGTH]

    return url_content


async def _extract_from_source(
    url: str,
    content: str,
    topic_name: str,
    goal_title: str,
    education_level: str,
    content_needs_str: str,
    raw_result: dict,
) -> SourceInfo:
    """Use LLM to extract structured knowledge from a single source."""
    settings = get_settings()

    system_prompt = EXTRACT_SYSTEM_PROMPT.format(
        topic_name=topic_name,
        goal_title=goal_title,
        education_level=education_level,
        content_needs=content_needs_str,
        score_rubric=SCORE_CALIBRATION_RUBRIC,
    )

    agent = Agent(
        create_model(settings.effective_extract_model),
        system_prompt=system_prompt,
        output_type=SourceInfo,
    )

    source_type = raw_result.get("search_type", "web")
    source_origin = raw_result.get("source", "")
    if source_origin == "user_resource":
        source_type = "user_material"
    elif source_type == "github":
        source_type = "repo"
    elif source_type == "scholar":
        source_type = "paper"
    else:
        source_type = "article"

    user_prompt = (
        f"Extract structured knowledge from this source.\n\n"
        f"Source URL: {url}\n"
        f"Source Title: {raw_result.get('title', 'Unknown')}\n"
        f"Source Type: {source_type}\n"
        f"Topic Group: {topic_name}\n\n"
        f"--- FULL CONTENT ---\n{content}\n--- END CONTENT ---"
    )

    async def _run():
        result = await agent.run(user_prompt)
        source = result.output
        # Ensure URL and topic_group are correct (override LLM if it changes them)
        source.url = url
        source.topic_group = topic_name
        return source

    return await run_with_retry(_run)


async def _analyze_codebase(
    url: str,
    owner: str,
    repo: str,
    topic_name: str,
    goal_title: str,
) -> tuple[CodebaseReference | None, list[CodingExercise]]:
    """Analyze a GitHub repo for educational value."""
    # Fetch repo structure and README
    readme = await github_fetch_readme(owner, repo)
    tree = await github_fetch_tree(owner, repo)

    if not readme and not tree:
        return None, []

    # Identify key files to read
    key_file_candidates = []
    if tree:
        important_patterns = [
            "train", "model", "main", "config", "run", "demo",
            "inference", "generate", "sample", "pipeline",
        ]
        for path in tree:
            filename = path.split("/")[-1].lower()
            if any(p in filename for p in important_patterns) and filename.endswith(".py"):
                key_file_candidates.append(path)

    # Fetch up to 3 key files
    key_file_contents = ""
    key_files_read = []
    for path in key_file_candidates[:3]:
        content = await github_fetch_file(owner, repo, path)
        if content:
            key_file_contents += f"\n\n--- {path} ---\n{content[:3000]}"
            key_files_read.append(path)

    settings = get_settings()

    prompt = EXTRACT_CODE_PROMPT.format(
        topic_name=topic_name,
        goal_title=goal_title,
        repo_name=f"{owner}/{repo}",
        readme_content=(readme or "No README found")[:5000],
        file_tree="\n".join(tree[:100]) if tree else "Could not fetch tree",
        key_file_contents=key_file_contents or "No key files fetched",
    )

    # Use a structured output model for the codebase analysis
    from pydantic import BaseModel

    class CodebaseAnalysis(BaseModel):
        architecture_summary: str = ""
        key_files: list[str] = []
        setup_instructions: str = ""
        suitability_score: float = 0.5
        coding_exercises: list[CodingExercise] = []

    agent = Agent(create_model(settings.effective_extract_model), output_type=CodebaseAnalysis)

    async def _run():
        result = await agent.run(prompt)
        return result.output

    try:
        analysis = await run_with_retry(_run)

        codebase_ref = CodebaseReference(
            repo_url=url,
            repo_name=f"{owner}/{repo}",
            stars=0,  # Will be updated from search results
            description="",
            main_language="Python",
            key_files=analysis.key_files or key_files_read,
            setup_instructions=analysis.setup_instructions,
            architecture_summary=analysis.architecture_summary,
            suitability_score=analysis.suitability_score,
        )

        return codebase_ref, analysis.coding_exercises
    except Exception as e:
        logger.warning(f"Codebase analysis failed for {owner}/{repo}: {e}")
        return None, []


async def run_extract_for_topic(
    topic_group: TopicGroup,
    raw_results: list[dict],
    goal_title: str,
    education_level: str,
) -> TopicResearchResult:
    """Run deep extraction for a single topic group.

    1. Rank raw results → pick best URLs
    2. Fetch full content from those URLs
    3. LLM extracts structured knowledge from each
    4. For code topics: analyze best GitHub repos
    5. Aggregate into TopicResearchResult
    """
    settings = get_settings()
    topic_name = topic_group.name
    content_needs = topic_group.content_needs
    content_needs_str = (
        f"needs_formulas={content_needs.needs_formulas}, "
        f"needs_numerical_data={content_needs.needs_numerical_data}, "
        f"needs_code_examples={content_needs.needs_code_examples}, "
        f"needs_working_codebase={content_needs.needs_working_codebase}, "
        f"needs_conceptual_depth={content_needs.needs_conceptual_depth}"
    )

    if not raw_results:
        return TopicResearchResult(
            topic_group=topic_name,
            sources=[],
            notes=f"No search results found for {topic_name}",
        )

    # Step 1: Rank URLs
    ranked_urls = await _rank_urls(topic_name, raw_results, MAX_SOURCES_PER_TOPIC)
    logger.info(f"Ranked {len(ranked_urls)} URLs for extraction in '{topic_name}'")

    # Build a lookup from URL to raw result
    url_to_raw = {r["url"]: r for r in raw_results if r.get("url")}

    # Step 2: Fetch full content (resource:// URLs use snippet as content)
    url_content = await _fetch_content(ranked_urls)
    # For resource:// URLs, content comes from the search snippet directly
    for url in ranked_urls:
        if url.startswith("resource://"):
            raw = url_to_raw.get(url, {})
            snippet = raw.get("snippet", "")
            prefix = raw.get("context_prefix", "")
            if snippet:
                url_content[url] = f"{prefix}\n{snippet}" if prefix else snippet
    logger.info(f"Fetched content from {len(url_content)} URLs for '{topic_name}'")

    # Step 3: Extract structured knowledge from each source
    # Gemini has tight RPM limits; Groq/Pollinations are more generous
    extract_delay = 2 if settings.effective_extract_model.startswith("google-gla:") else 1
    sources: list[SourceInfo] = []
    for url in ranked_urls:
        content = url_content.get(url)
        if not content:
            # If we couldn't fetch content, create a basic entry from search snippet
            raw = url_to_raw.get(url, {})
            if raw.get("snippet"):
                sources.append(SourceInfo(
                    topic_group=topic_name,
                    source_type="article",
                    title=raw.get("title", "Unknown"),
                    url=url,
                    summary=raw.get("snippet", ""),
                    key_concepts=[],
                    relevance_score=0.4,
                    credibility_score=0.4,
                    content_extract=raw.get("snippet", "")[:300],
                ))
            continue

        raw = url_to_raw.get(url, {})
        try:
            source = await _extract_from_source(
                url=url,
                content=content,
                topic_name=topic_name,
                goal_title=goal_title,
                education_level=education_level,
                content_needs_str=content_needs_str,
                raw_result=raw,
            )
            sources.append(source)
        except Exception as e:
            logger.warning(f"Extraction failed for {url}: {e}")
            # Fall back to basic entry
            sources.append(SourceInfo(
                topic_group=topic_name,
                source_type="article",
                title=raw.get("title", "Unknown"),
                url=url,
                summary=raw.get("snippet", "Content extraction failed"),
                key_concepts=[],
                relevance_score=0.3,
                credibility_score=0.3,
                content_extract=raw.get("snippet", "")[:300],
            ))

        # Brief pause between LLM calls (Groq has higher RPM limits)
        await asyncio.sleep(extract_delay)

    # Filter out low-relevance sources (garbage filter)
    sources = [s for s in sources if s.relevance_score >= 0.5]

    # Step 4: Codebase analysis for repos (if needed)
    codebase_references: list[CodebaseReference] = []
    coding_exercises: list[CodingExercise] = []

    if content_needs.needs_working_codebase or content_needs.needs_code_examples:
        github_results = [r for r in raw_results if r.get("search_type") == "github"]
        # Analyze top 2 repos
        for r in github_results[:2]:
            parsed = _parse_github_url(r.get("url", ""))
            if not parsed:
                continue
            owner, repo = parsed
            try:
                codebase_ref, exercises = await _analyze_codebase(
                    url=r["url"],
                    owner=owner,
                    repo=repo,
                    topic_name=topic_name,
                    goal_title=goal_title,
                )
                if codebase_ref:
                    codebase_ref.stars = r.get("stars", 0)
                    codebase_ref.description = r.get("snippet", "")
                    codebase_ref.main_language = r.get("language", "Python") or "Python"
                    codebase_references.append(codebase_ref)
                coding_exercises.extend(exercises)
            except Exception as e:
                logger.warning(f"Codebase analysis failed for {r.get('url')}: {e}")
            await asyncio.sleep(extract_delay)

    # Step 5: Aggregate formulas and numerical data from all sources
    all_formulas: list[MathFormula] = []
    all_numerical: list[NumericalExample] = []
    for s in sources:
        if s.extracted_content:
            all_formulas.extend(s.extracted_content.formulas)
            all_numerical.extend(s.extracted_content.numerical_examples)

    # Deduplicate formulas by normalized plain_text
    seen_formulas: set[str] = set()
    unique_formulas: list[MathFormula] = []
    for f in all_formulas:
        key = f.plain_text.strip().lower().replace(" ", "")
        if key not in seen_formulas:
            seen_formulas.add(key)
            unique_formulas.append(f)
    all_formulas = unique_formulas

    # Deduplicate analogies across sources by normalized analogy text
    seen_analogies: set[str] = set()
    for s in sources:
        if s.extracted_content and s.extracted_content.analogies:
            unique = []
            for a in s.extracted_content.analogies:
                key = a.analogy.strip().lower()[:80]
                if key not in seen_analogies:
                    seen_analogies.add(key)
                    unique.append(a)
            s.extracted_content.analogies = unique

    # Filter trivial code snippets (install commands, one-liners)
    for s in sources:
        if s.extracted_content and s.extracted_content.code_snippets:
            s.extracted_content.code_snippets = [
                cs for cs in s.extracted_content.code_snippets
                if len(cs.code.strip()) >= 50
                and cs.language.lower() not in ("bash", "shell", "sh", "console")
            ]

    notes = (
        f"Extracted deep content from {len(sources)} sources. "
        f"Formulas: {len(all_formulas)}, Code repos analyzed: {len(codebase_references)}, "
        f"Exercises: {len(coding_exercises)}"
    )

    return TopicResearchResult(
        topic_group=topic_name,
        sources=sources,
        notes=notes,
        codebase_references=codebase_references,
        coding_exercises=coding_exercises,
        topic_formulas=all_formulas,
        topic_numerical_data=all_numerical,
    )
