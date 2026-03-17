"""Stage 2: Deterministic search — no LLM, just API calls with deduplication.

Includes hybrid search integration for user-uploaded resources (RAG pipeline).
"""

import asyncio
import logging

from app.models.domain import TopicTree, TopicGroup
from app.tools.tavily import tavily_search
from app.tools.serper import serper_scholar_search
from app.tools.github import github_repo_search
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

# Delay between API calls to respect rate limits
SEARCH_DELAY_SECONDS = 2


async def _execute_search(
    query: str,
    search_type: str,
    search_depth: str = "basic",
) -> list[dict]:
    """Execute a single search query using the appropriate API."""
    if search_type == "web":
        results = await tavily_search(query, max_results=5, search_depth=search_depth)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "source": "tavily",
                "search_type": "web",
            }
            for r in results
        ]
    elif search_type == "scholar":
        results = await serper_scholar_search(query, num_results=5)
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "year": r.get("year"),
                "cited_by": r.get("cited_by"),
                "source": "serper",
                "search_type": "scholar",
            }
            for r in results
        ]
    elif search_type == "github":
        results = await github_repo_search(query, max_results=5)
        return [
            {
                "title": r.get("name", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
                "stars": r.get("stars", 0),
                "language": r.get("language"),
                "source": "github",
                "search_type": "github",
            }
            for r in results
        ]
    else:
        logger.warning(f"Unknown search_type: {search_type}, falling back to web")
        return await _execute_search(query, "web", search_depth)


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication (strip trailing slash, fragment, etc.)."""
    url = url.rstrip("/")
    # Remove fragment
    if "#" in url:
        url = url.split("#")[0]
    # Remove common tracking params
    if "?" in url:
        base, params = url.split("?", 1)
        # Keep params for GitHub (they're meaningful) but strip for others
        if "github.com" not in base:
            url = base
    return url.lower()


async def run_search(
    topic_tree: TopicTree,
    goal_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, list[dict]]:
    """Execute all search queries across all topics.

    Returns: {topic_name: [raw_results]} with duplicates removed globally.
    If goal_id and user_id are provided, also searches user-uploaded resources
    via hybrid search (vector + full-text, RRF fusion).
    """
    seen_urls: set[str] = set()
    results_by_topic: dict[str, list[dict]] = {}

    for topic_group in topic_tree.topic_groups:
        topic_results: list[dict] = []
        is_high_priority = topic_group.content_needs.priority == "high"

        for sq in topic_group.search_queries:
            # Use advanced search for high-priority web queries
            depth = "advanced" if (is_high_priority and sq.search_type == "web") else "basic"

            search_results = await _execute_search(sq.query, sq.search_type, depth)

            # Deduplicate across all topics
            for r in search_results:
                url = r.get("url", "")
                if not url:
                    continue
                normalized = _normalize_url(url)
                if normalized in seen_urls:
                    continue
                seen_urls.add(normalized)
                topic_results.append(r)

            # Pace API calls
            await asyncio.sleep(SEARCH_DELAY_SECONDS)

        results_by_topic[topic_group.name] = topic_results
        logger.info(
            f"Search complete for '{topic_group.name}': {len(topic_results)} unique results"
        )

    # Merge user resource results if available
    if goal_id and user_id:
        resource_results = await _merge_user_resource_results(
            topic_tree, goal_id, user_id
        )
        for topic_name, res_results in resource_results.items():
            if topic_name in results_by_topic:
                # Prepend resource results (slightly higher priority)
                results_by_topic[topic_name] = res_results + results_by_topic[topic_name]
            else:
                results_by_topic[topic_name] = res_results

    total = sum(len(v) for v in results_by_topic.values())
    logger.info(f"Total search results across all topics: {total} (deduplicated)")
    return results_by_topic


async def _merge_user_resource_results(
    topic_tree: TopicTree,
    goal_id: str,
    user_id: str,
) -> dict[str, list[dict]]:
    """Search user-uploaded resources via hybrid search for each topic.

    Returns results formatted like web search results with resource:// URLs.
    Gracefully returns empty if no chunks exist yet.
    """
    sb = get_supabase()
    results: dict[str, list[dict]] = {}

    # Quick check: are there any ready resources for this goal?
    resource_check = (
        sb.table("user_resources")
        .select("id")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .eq("status", "ready")
        .limit(1)
        .execute()
    )
    if not resource_check.data:
        return results

    try:
        from app.services.embeddings import embed_query
    except ImportError:
        logger.warning("Embeddings service not available, skipping user resource search")
        return results

    for topic_group in topic_tree.topic_groups:
        topic_results: list[dict] = []
        query = topic_group.name

        try:
            # Embed the topic query
            query_embedding = await embed_query(query)

            # Call hybrid_search RPC
            search_result = sb.rpc("hybrid_search", {
                "query_embedding": query_embedding,
                "query_text": query,
                "p_goal_id": goal_id,
                "p_user_id": user_id,
                "match_count": 5,
                "vector_weight": 0.5,
                "text_weight": 0.5,
                "similarity_threshold": 0.3,
            }).execute()

            if search_result.data:
                for chunk in search_result.data:
                    # Build a synthetic URL for the resource chunk
                    resource_url = f"resource://{chunk['resource_id']}/{chunk['chunk_id']}"
                    topic_results.append({
                        "title": f"[Your Material] {chunk.get('file_name', 'Uploaded Document')}",
                        "url": resource_url,
                        "snippet": chunk.get("content", "")[:500],
                        "source": "user_resource",
                        "search_type": "web",
                        "context_prefix": chunk.get("context_prefix", ""),
                        "page_number": chunk.get("page_number"),
                        "rrf_score": chunk.get("rrf_score", 0),
                    })

            if topic_results:
                results[topic_group.name] = topic_results
                logger.info(
                    f"User resource search for '{topic_group.name}': "
                    f"{len(topic_results)} chunks found"
                )
        except Exception as e:
            logger.warning(f"User resource search failed for '{topic_group.name}': {e}")

    return results
