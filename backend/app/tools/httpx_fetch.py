import logging
import re

import httpx

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    """Basic HTML tag stripping to extract text content."""
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def httpx_fetch_page(url: str) -> str | None:
    """Fetch a web page and extract its text content.

    Fallback for when Tavily extract is unavailable.
    Returns extracted text (up to 10k chars) or None on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; PedagoraBot/1.0; +https://pedagora.dev)"
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            text = _strip_html(response.text)
        else:
            text = response.text

        return text[:10_000] if text else None
    except Exception as e:
        logger.debug(f"httpx_fetch_page failed for {url}: {e}")
        return None
