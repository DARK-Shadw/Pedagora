"""Pollinations.ai image generation via authenticated GET endpoint.

Usage:
    from app.services.image_gen import generate_image

    path = await generate_image(
        "Educational diagram showing a neural network mapping latent space to digits",
        output_dir="/tmp/images",
    )
    # path = "/tmp/images/gen_a3f8b2c1d0.jpg" (or None on failure)
"""

import hashlib
import logging
import os
import urllib.parse

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://gen.pollinations.ai/image"
DEFAULT_MODEL = "flux"
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
REQUEST_TIMEOUT = 60.0  # Image gen can take 10-30s


async def generate_image(
    prompt: str,
    *,
    output_dir: str,
    filename: str | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    model: str = DEFAULT_MODEL,
    seed: int = 42,
) -> str | None:
    """Generate an image via Pollinations and save to disk.

    Returns the local file path on success, None on failure.
    Uses content-hash filenames so identical prompts are cached.
    """
    settings = get_settings()
    api_key = settings.pollinations_api_key
    if not api_key:
        logger.error("[ImageGen] No pollinations_api_key configured")
        return None

    encoded_prompt = urllib.parse.quote(prompt)
    url = (
        f"{BASE_URL}/{encoded_prompt}"
        f"?model={model}&width={width}&height={height}"
        f"&seed={seed}&nologo=true&nofeed=true"
    )

    if not filename:
        h = hashlib.md5(prompt.encode()).hexdigest()[:10]
        filename = f"gen_{h}.jpg"

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    # Cache hit — same prompt hash → same file already on disk
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
        logger.info(f"[ImageGen] Cache hit: {output_path}")
        return output_path

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                logger.error(
                    f"[ImageGen] Unexpected content-type: {content_type}, "
                    f"body[:200]={resp.text[:200]}"
                )
                return None

            with open(output_path, "wb") as f:
                f.write(resp.content)

            size_kb = len(resp.content) // 1024
            logger.info(f"[ImageGen] Generated {size_kb}KB image: {output_path}")
            return output_path

    except httpx.HTTPStatusError as e:
        logger.error(f"[ImageGen] HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"[ImageGen] Failed: {e}")
        return None
