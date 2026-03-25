"""LLM-powered Manim code generation from animation specs."""

import logging
import re

from pydantic_ai import Agent

from app.agents.animation.manim_reference import MANIM_API_REFERENCE
from app.agents.animation.prompts import ANIMATION_CODEGEN_PROMPT, ANIMATION_FIX_PROMPT
from app.agents.models import create_model
from app.agents.retry import run_with_retry
from app.config import get_settings

logger = logging.getLogger(__name__)


def _extract_python_code(text: str) -> str:
    """Extract Python code from LLM response, stripping markdown fences."""
    # Try ```python ... ``` block
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try ``` ... ```
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If it starts with "from manim" or "import", assume it's raw code
    if text.strip().startswith(("from manim", "import ")):
        return text.strip()
    # Last resort: return as-is
    return text.strip()


async def generate_manim_code(
    animation_spec: dict,
    search_results: str,
    prepared_data: dict | None = None,
    model_string: str | None = None,
) -> str:
    """Generate Manim scene code from an animation spec.

    Args:
        prepared_data: Dict from data_prep.prepare_animation_data() with file paths.
    Returns raw Python code string ready to be written to a .py file.
    """
    settings = get_settings()
    effective_model = model_string or settings.animation_model

    # Format prepared data for the prompt
    if prepared_data and prepared_data.get("image_path"):
        data_section = (
            f"Dataset: {prepared_data.get('dataset', 'unknown')}\n"
            f"Description: {prepared_data.get('description', '')}\n"
            f"Main image file: {prepared_data['image_path']}\n"
        )
        files = prepared_data.get("files", [])
        if files:
            data_section += f"All files ({len(files)}):\n"
            for f in files[:10]:
                data_section += f"  {f}\n"
        noisy = prepared_data.get("noisy_series", [])
        if noisy:
            data_section += f"Noisy versions ({len(noisy)} files, increasing noise):\n"
            for f in noisy:
                data_section += f"  {f}\n"
        data_section += (
            f"\nIMPORTANT: Use ImageMobject(\"{prepared_data['image_path']}\") to load the image.\n"
            f"Set height: img.set_height(5). Place at center: img.move_to(ORIGIN).\n"
            f"For noisy versions, load each file with ImageMobject(path)."
        )
    else:
        data_section = "No prepared data. Generate synthetic data with numpy."

    prompt = ANIMATION_CODEGEN_PROMPT.format(
        animation_type=animation_spec.get("animation_type", ""),
        description=animation_spec.get("description", ""),
        duration_seconds=animation_spec.get("duration_seconds", 10),
        parameters=animation_spec.get("parameters", {}),
        prepared_data=data_section,
        reference_code=animation_spec.get("reference_code", "None provided"),
        reference_formula_latex=animation_spec.get("reference_formula_latex", ""),
        reference_formula_vars=animation_spec.get("reference_formula_vars", {}),
        reference_values=animation_spec.get("reference_values", {}),
        search_results=search_results,
        manim_reference=MANIM_API_REFERENCE,
    )

    agent = Agent(create_model(effective_model), output_type=str)

    async def _run():
        result = await agent.run(prompt)
        return result.output

    raw_output = await run_with_retry(_run)
    code = _extract_python_code(raw_output)

    # Basic validation: must contain AnimationScene class
    if "class AnimationScene" not in code:
        # Try to fix: wrap in class if it looks like construct() body
        if "self.play" in code or "self.wait" in code:
            code = (
                "from manim import *\nimport numpy as np\n\n"
                "class AnimationScene(Scene):\n"
                "    def construct(self):\n"
                + "\n".join(f"        {line}" for line in code.split("\n"))
            )
        else:
            logger.warning("Generated code missing AnimationScene class")

    return code


async def fix_manim_code(
    code: str,
    error: str,
    model_string: str | None = None,
) -> str:
    """Fix broken Manim code using the LLM with the error traceback."""
    settings = get_settings()
    effective_model = model_string or settings.animation_model

    prompt = ANIMATION_FIX_PROMPT.format(
        error=error[-1000:],  # Last 1000 chars of error
        code=code,
    )

    agent = Agent(create_model(effective_model), output_type=str)

    async def _run():
        result = await agent.run(prompt)
        return result.output

    raw_output = await run_with_retry(_run)
    return _extract_python_code(raw_output)
