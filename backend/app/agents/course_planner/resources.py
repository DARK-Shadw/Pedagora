"""Fetch student's uploaded resources relevant to a lesson via hybrid_search."""

import logging

from app.models.course_plan import ResourceReference
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


async def fetch_lesson_resources(
    lesson_title: str,
    topics_covered: list[str],
    goal_id: str,
    user_id: str,
    max_results: int = 5,
) -> list[ResourceReference]:
    """Query hybrid_search for student resource chunks relevant to a lesson.

    Returns an empty list if:
    - No user resources exist for this goal
    - Jina API key is not configured
    - Any error occurs (graceful degradation)
    """
    try:
        from app.config import get_settings
        settings = get_settings()

        if not settings.jina_api_key:
            return []

        # Build search query from lesson context
        query_text = f"{lesson_title}: {', '.join(topics_covered)}"

        # Embed the query
        from app.services.embeddings import embed_query
        query_embedding = await embed_query(query_text)

        if not query_embedding:
            return []

        # Call hybrid_search RPC
        sb = get_supabase()
        result = sb.rpc("hybrid_search", {
            "query_embedding": query_embedding,
            "query_text": query_text,
            "p_goal_id": goal_id,
            "p_user_id": user_id,
            "match_count": max_results,
            "vector_weight": 0.5,
            "text_weight": 0.5,
            "similarity_threshold": 0.3,
        }).execute()

        if not result.data:
            return []

        # Map chunks to ResourceReference objects
        refs = []
        for chunk in result.data:
            refs.append(ResourceReference(
                file_name=chunk.get("file_name", ""),
                page_number=chunk.get("page_number"),
                section_title=chunk.get("context_prefix", ""),
                quote_snippet=(chunk.get("content", "")[:150]).strip(),
                relevance_note=f"RRF score: {chunk.get('rrf_score', 0):.3f}",
            ))

        logger.info(
            f"Found {len(refs)} student resource chunks for lesson '{lesson_title}'"
        )
        return refs

    except Exception as e:
        logger.warning(f"Student resource fetch failed for '{lesson_title}': {e}")
        return []
