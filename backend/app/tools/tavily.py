from tavily import AsyncTavilyClient

from app.config import get_settings

_client: AsyncTavilyClient | None = None


def _get_client() -> AsyncTavilyClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return _client


async def tavily_search(
    query: str, max_results: int = 5, search_depth: str = "basic"
) -> list[dict]:
    """Search the web using Tavily. Returns list of results or [] on failure."""
    try:
        client = _get_client()
        response = await client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=False,
        )
        results = []
        for r in response.get("results", []):
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                }
            )
        return results
    except Exception:
        return []
