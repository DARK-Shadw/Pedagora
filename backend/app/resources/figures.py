"""Figure extraction and VLM-powered description for RAG pipeline."""

import base64
import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class FigureDescription:
    description: str
    concepts: list[str]
    figure_type: str  # 'diagram', 'chart', 'photo', 'equation', 'table'


async def describe_figure(
    image_bytes: bytes,
    caption: str | None = None,
    context: str | None = None,
) -> FigureDescription:
    """Use VLM to describe a figure and extract concepts.

    Uses OpenRouter API with Nemotron Nano 12B VL model.
    Falls back to caption-only description if VLM fails.
    """
    settings = get_settings()

    if not settings.openrouter_api_key:
        logger.warning("No OpenRouter API key, using caption-only fallback for figure")
        return FigureDescription(
            description=caption or "Figure from uploaded document",
            concepts=[],
            figure_type="diagram",
        )

    # Encode image to base64
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Analyze this educational figure/diagram. Provide:\n"
        "1. A clear description of what the figure shows (2-3 sentences)\n"
        "2. Key concepts illustrated in the figure (as a comma-separated list)\n"
        "3. The type of figure: diagram, chart, photo, equation, or table\n\n"
        f"{'Caption: ' + caption if caption else ''}\n"
        f"{'Context: ' + context if context else ''}\n\n"
        "Respond in this exact format:\n"
        "DESCRIPTION: <your description>\n"
        "CONCEPTS: <concept1>, <concept2>, ...\n"
        "TYPE: <figure_type>"
    )

    try:
        # Extract the actual model name from the config string
        vlm_model = settings.vlm_model
        if vlm_model.startswith("openrouter:"):
            vlm_model = vlm_model.removeprefix("openrouter:")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": vlm_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{b64_image}",
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()

        text = data["choices"][0]["message"]["content"]
        return _parse_vlm_response(text)

    except Exception as e:
        logger.warning(f"VLM figure description failed: {e}")
        return FigureDescription(
            description=caption or "Figure from uploaded document",
            concepts=[],
            figure_type="diagram",
        )


def _parse_vlm_response(text: str) -> FigureDescription:
    """Parse the structured VLM response."""
    description = ""
    concepts: list[str] = []
    figure_type = "diagram"

    for line in text.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("DESCRIPTION:"):
            description = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CONCEPTS:"):
            raw = line.split(":", 1)[1].strip()
            concepts = [c.strip() for c in raw.split(",") if c.strip()]
        elif line.upper().startswith("TYPE:"):
            raw_type = line.split(":", 1)[1].strip().lower()
            if raw_type in ("diagram", "chart", "photo", "equation", "table"):
                figure_type = raw_type

    if not description:
        description = text[:300]

    return FigureDescription(
        description=description,
        concepts=concepts,
        figure_type=figure_type,
    )
