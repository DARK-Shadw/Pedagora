import logging

from tavily import AsyncTavilyClient

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncTavilyClient | None = None


def _get_client() -> AsyncTavilyClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return _client


async def tavily_extract(urls: list[str]) -> list[dict]:
    """Extract full page content from URLs using Tavily extract API.

    Input: list of URLs (max 5 per call, Tavily limit).
    Output: list of {url, raw_content} dicts.
    Returns empty list on failure.
    """
    if not urls:
        return []

    # Tavily extract limit: 5 URLs per call
    batch_size = 5
    all_results = []

    try:
        client = _get_client()
        for i in range(0, len(urls), batch_size):
            batch = urls[i : i + batch_size]
            response = await client.extract(urls=batch)
            for r in response.get("results", []):
                all_results.append(
                    {
                        "url": r.get("url", ""),
                        "raw_content": r.get("raw_content", ""),
                    }
                )
    except Exception as e:
        logger.warning(f"Tavily extract failed: {e}")

    return all_results
