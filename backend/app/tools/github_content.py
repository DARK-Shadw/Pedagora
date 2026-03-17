import base64
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    settings = get_settings()
    h = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


async def github_fetch_readme(owner: str, repo: str) -> str | None:
    """Fetch the README content (markdown) from a GitHub repo."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/readme",
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("content", "")
            encoding = data.get("encoding", "base64")
            if encoding == "base64" and content:
                return base64.b64decode(content).decode("utf-8", errors="replace")
            return content or None
    except Exception as e:
        logger.debug(f"Failed to fetch README for {owner}/{repo}: {e}")
        return None


async def github_fetch_file(
    owner: str, repo: str, path: str
) -> str | None:
    """Fetch a single file's content from a GitHub repo."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()

            # GitHub returns base64 for files up to 1MB via contents API
            content = data.get("content", "")
            encoding = data.get("encoding", "base64")
            if encoding == "base64" and content:
                decoded = base64.b64decode(content).decode("utf-8", errors="replace")
                # Truncate large files to 10k chars
                return decoded[:10_000]
            return content[:10_000] if content else None
    except Exception as e:
        logger.debug(f"Failed to fetch file {path} from {owner}/{repo}: {e}")
        return None


async def github_fetch_tree(owner: str, repo: str) -> list[str] | None:
    """Fetch the full file tree of a GitHub repo (non-recursive top level + key dirs)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Use the git tree API with recursive flag
            # First get the default branch
            repo_resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}",
                headers=_headers(),
            )
            repo_resp.raise_for_status()
            default_branch = repo_resp.json().get("default_branch", "main")

            # Get recursive tree
            tree_resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{default_branch}",
                headers=_headers(),
                params={"recursive": "1"},
            )
            tree_resp.raise_for_status()
            data = tree_resp.json()

        paths = []
        for item in data.get("tree", []):
            if item.get("type") == "blob":
                paths.append(item["path"])

        # Limit to 500 paths to avoid overwhelming downstream processing
        return paths[:500]
    except Exception as e:
        logger.debug(f"Failed to fetch tree for {owner}/{repo}: {e}")
        return None
