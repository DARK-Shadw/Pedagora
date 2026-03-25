"""Targeted search for Manim reference code relevant to an animation spec."""

import logging

from app.tools.tavily import tavily_search
from app.tools.tavily_extract import tavily_extract
from app.tools.github import github_repo_search

logger = logging.getLogger(__name__)


async def search_manim_reference(
    animation_type: str,
    description: str,
    max_web_results: int = 2,
) -> str:
    """Search for Manim code examples relevant to this animation.

    Returns a formatted string of reference code snippets for the LLM prompt.
    Returns "No reference code found." if search fails or finds nothing.
    """
    # Build targeted queries from the first 80 chars of description
    concept = description[:80].replace('"', "").replace("'", "")

    try:
        # Web search for Manim examples
        web_results = await tavily_search(
            f"manim {animation_type} {concept} python code example",
            max_results=max_web_results,
        )

        # GitHub search for Manim repos
        github_results = await github_repo_search(
            f"manim {concept}",
            max_results=2,
            language="Python",
        )

        # Collect URLs to extract content from
        urls = []
        for r in web_results[:2]:
            if r.get("url"):
                urls.append(r["url"])
        for r in github_results[:1]:
            if r.get("url"):
                urls.append(r["url"])

        if not urls:
            return "No reference code found."

        # Extract full content from top URLs
        extracted = await tavily_extract(urls)

        # Format results (truncate to fit in prompt)
        formatted = []
        total_chars = 0
        for e in extracted:
            content = e.get("raw_content", "")
            if not content:
                continue
            # Take first 600 chars of each result
            snippet = content[:600].strip()
            if snippet:
                formatted.append(f"--- {e.get('url', 'unknown')} ---\n{snippet}")
                total_chars += len(snippet)
                if total_chars > 1500:
                    break

        result = "\n\n".join(formatted)
        if result:
            logger.info(
                f"Found {len(formatted)} Manim references for {animation_type}"
            )
            return result

    except Exception as e:
        logger.warning(f"Manim reference search failed: {e}")

    return "No reference code found."
