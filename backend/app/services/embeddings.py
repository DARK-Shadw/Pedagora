"""
Jina Embeddings v3 API client for the Pedagora RAG pipeline.

Uses Jina's embedding API to produce 768-dim vectors for document chunks
and search queries. Batches large inputs to stay within API limits.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_JINA_URL = "https://api.jina.ai/v1/embeddings"
_MODEL = "jina-embeddings-v3"
_BATCH_SIZE = 64  # Jina supports up to 2048, but keep requests small
_TIMEOUT = 60.0  # seconds per HTTP request


async def _call_jina(
    texts: list[str],
    *,
    task: str,
) -> list[list[float]]:
    """Low-level call to the Jina embeddings endpoint for a single batch."""
    settings = get_settings()

    if not settings.jina_api_key:
        raise RuntimeError("jina_api_key is not configured")

    headers = {
        "Authorization": f"Bearer {settings.jina_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": _MODEL,
        "input": texts,
        "task": task,
        "dimensions": settings.embedding_dimension,
        "late_chunking": False,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(_JINA_URL, json=payload, headers=headers)

    if response.status_code != 200:
        logger.error(
            "Jina API error %d: %s",
            response.status_code,
            response.text[:500],
        )
        response.raise_for_status()

    data = response.json()
    # Jina returns {"data": [{"index": 0, "embedding": [...]}, ...]}
    # Sort by index to guarantee order matches input order.
    sorted_items = sorted(data["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in sorted_items]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed document chunks using the retrieval.passage task.

    Splits *texts* into batches of up to ``_BATCH_SIZE`` and concatenates
    the results so the returned list is in the same order as the input.

    Args:
        texts: List of chunk strings to embed.

    Returns:
        A list of embedding vectors, one per input text.

    Raises:
        RuntimeError: If the Jina API key is not set.
        httpx.HTTPStatusError: On non-200 responses from Jina.
    """
    if not texts:
        return []

    logger.info("Embedding %d texts in batches of %d", len(texts), _BATCH_SIZE)
    all_embeddings: list[list[float]] = []

    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        batch_num = start // _BATCH_SIZE + 1
        total_batches = (len(texts) + _BATCH_SIZE - 1) // _BATCH_SIZE
        logger.debug("Processing batch %d/%d (%d texts)", batch_num, total_batches, len(batch))

        try:
            embeddings = await _call_jina(batch, task="retrieval.passage")
            all_embeddings.extend(embeddings)
        except httpx.HTTPStatusError:
            logger.exception("Failed to embed batch %d/%d", batch_num, total_batches)
            raise
        except Exception:
            logger.exception("Unexpected error embedding batch %d/%d", batch_num, total_batches)
            raise

    logger.info("Embedded %d texts -> %d vectors", len(texts), len(all_embeddings))
    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single search query using the retrieval.query task.

    Args:
        text: The search query string.

    Returns:
        A single embedding vector.

    Raises:
        RuntimeError: If the Jina API key is not set.
        httpx.HTTPStatusError: On non-200 responses from Jina.
    """
    if not text.strip():
        raise ValueError("Query text must not be empty")

    logger.debug("Embedding query: %.80s...", text)

    try:
        embeddings = await _call_jina([text], task="retrieval.query")
    except httpx.HTTPStatusError:
        logger.exception("Failed to embed query")
        raise
    except Exception:
        logger.exception("Unexpected error embedding query")
        raise

    return embeddings[0]
