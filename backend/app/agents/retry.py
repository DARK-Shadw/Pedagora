import asyncio
import logging
import re
from typing import TypeVar, Callable, Awaitable

T = TypeVar("T")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3


async def run_with_retry(fn: Callable[[], Awaitable[T]], max_retries: int = MAX_RETRIES) -> T:
    """Run an async function with exponential backoff on 429 rate limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            error_str = str(e)
            if "429" not in error_str or attempt == max_retries:
                raise

            # Extract retry delay from error if available
            delay = _extract_retry_delay(error_str)
            if delay is None:
                delay = 15 * (2 ** attempt)  # 15s, 30s, 60s

            logger.warning(
                f"Rate limited (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.0f}s..."
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Unreachable")


def _extract_retry_delay(error_str: str) -> float | None:
    """Extract retry delay from Gemini or Groq 429 error messages."""
    # Gemini format: retryDelay: "30.5s"
    match = re.search(r"retryDelay.*?(\d+(?:\.\d+)?)s", error_str)
    if match:
        return float(match.group(1)) + 2  # add 2s buffer

    # Groq format: "Please try again in 1.5s" or "retry after 2s"
    match = re.search(r"(?:try again in|retry.after)\s*(\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) + 2

    # Groq format: "Please try again in 1m30s" or similar
    match = re.search(r"(?:try again in|retry.after)\s*(\d+)m(\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 60 + float(match.group(2)) + 2

    return None
