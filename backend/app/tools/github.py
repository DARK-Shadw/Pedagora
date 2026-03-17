import httpx

from app.config import get_settings

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


async def github_repo_search(query: str, max_results: int = 5) -> list[dict]:
    """Search GitHub for relevant repositories. Returns list of results or [] on failure."""
    try:
        settings = get_settings()
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                GITHUB_SEARCH_URL,
                headers=headers,
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": max_results,
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("items", []):
            results.append(
                {
                    "name": r.get("full_name", ""),
                    "url": r.get("html_url", ""),
                    "description": r.get("description", ""),
                    "stars": r.get("stargazers_count", 0),
                    "language": r.get("language"),
                    "topics": r.get("topics", []),
                    "updated_at": r.get("updated_at"),
                }
            )
        return results
    except Exception:
        return []
