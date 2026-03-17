import httpx

from app.config import get_settings

SERPER_SCHOLAR_URL = "https://google.serper.dev/scholar"


async def serper_scholar_search(query: str, num_results: int = 5) -> list[dict]:
    """Search Google Scholar via Serper. Returns list of results or [] on failure."""
    try:
        settings = get_settings()
        if not settings.serper_api_key:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                SERPER_SCHOLAR_URL,
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num_results},
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("organic", []):
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                    "year": r.get("year"),
                    "cited_by": r.get("citedBy", {}).get("total"),
                }
            )
        return results
    except Exception:
        return []
