"""Prompt composer — assembles modular recipes into system + user prompts.

Instead of a single mega-prompt, the composer selects only the recipes
relevant to each frame's visual type, keeping the prompt small, focused,
and high-quality.

Usage:
    system, user = compose(frame, available_images=None)
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.animation_v2.recipes import ALL_RECIPES, RECIPE_BY_ID
from app.agents.animation_v2.recipes.core import (
    CORE_SYSTEM,
    CORE_USER_HEADER,
    CORE_USER_FOOTER,
)

logger = logging.getLogger(__name__)

# ── Mapping from course-planner visual_type / animation_type → recipe IDs ──
#
# Primary: exact match on visual_type or animation_type fields.
# These are the types defined in models/course_plan.py.

TYPE_TO_RECIPES: dict[str, list[str]] = {
    # VisualFrame.visual_type values
    "animation": [],          # generic — rely on keyword matching
    "equation": ["equation"],
    "diagram": ["flowchart"],
    "code": ["code"],
    "interactive": [],        # handled separately
    "split": ["comparison"],
    "blackboard": [],
    "image": [],
    "image_sequence": [],

    # AnimationSpec.animation_type values
    "diagram_build": ["flowchart"],
    "equation_reveal": ["equation"],
    "graph_plot": ["coordinate"],
    "code_walkthrough": ["code"],
    "comparison": ["comparison"],
    "process_flow": ["flowchart"],
    "3d_visualization": [],   # routed to Manim, not browser
    "data_animation": ["coordinate"],
}

# ── Maximum recipes per prompt to avoid bloat ──
MAX_RECIPES = 4


def _score_recipe(recipe_module, text: str) -> int:
    """Count how many keywords from a recipe match in the text."""
    text_lower = text.lower()
    return sum(1 for kw in recipe_module.KEYWORDS if kw in text_lower)


def select_recipes(frame: dict) -> list:
    """Select which recipe modules are relevant for a frame.

    Strategy:
    1. Start with recipes mapped from visual_type / animation_type
    2. Score all recipes by keyword matches in visual_spec.description + step descriptions
    3. Add top-scoring recipes up to MAX_RECIPES total
    4. Always include at least 1 recipe (fall back to highest-scoring)
    """
    selected_ids: list[str] = []

    # 1. Type-based selection
    visual_type = frame.get("visual_type", "animation")
    if visual_type in TYPE_TO_RECIPES:
        selected_ids.extend(TYPE_TO_RECIPES[visual_type])

    # Also check animation_type if present in visual_spec
    vspec = frame.get("visual_spec", {})
    anim_type = vspec.get("animation_type", "")
    if anim_type and anim_type in TYPE_TO_RECIPES:
        for rid in TYPE_TO_RECIPES[anim_type]:
            if rid not in selected_ids:
                selected_ids.append(rid)

    # 2. Build searchable text from frame
    desc = vspec.get("description", "")
    steps = frame.get("steps", [])
    step_text = " ".join(
        s.get("description", "") + " " + s.get("narration_spoken", "")
        for s in steps
    )
    search_text = f"{desc} {step_text}"

    # 3. Score all recipes (require ≥2 keyword hits to avoid false positives)
    scored = []
    for recipe in ALL_RECIPES:
        if recipe.ID in selected_ids:
            continue
        score = _score_recipe(recipe, search_text)
        if score >= 2:
            scored.append((score, recipe.ID))

    scored.sort(key=lambda x: -x[0])

    # 4. Fill up to MAX_RECIPES
    for score, rid in scored:
        if len(selected_ids) >= MAX_RECIPES:
            break
        selected_ids.append(rid)

    # 5. Fallback: if nothing matched, pick the highest-scoring recipe
    if not selected_ids and scored:
        selected_ids.append(scored[0][1])

    # 6. Resolve to modules
    recipes = []
    for rid in selected_ids:
        if rid in RECIPE_BY_ID:
            recipes.append(RECIPE_BY_ID[rid])

    logger.info(
        "Selected recipes for frame %s: %s",
        frame.get("frame_id", "?"),
        [r.ID for r in recipes],
    )
    return recipes


def _build_css_section(recipes: list) -> str:
    """Build the CSS documentation section from selected recipes."""
    parts = [
        # Always include base components
        "READY-MADE CSS COMPONENTS:",
        "  .card          — dark card with border and rounded corners",
        "  .card-accent   — card with blue left border",
        "  .bar           — progress bar container, .bar-fill — the fill",
        "  .hidden        — opacity:0",
        "  .center-abs    — centered absolute positioning",
        "  .glow-blue / .glow-green / .glow-yellow / .glow-purple — box-shadow glows",
    ]
    for recipe in recipes:
        if hasattr(recipe, "CSS_DOCS") and recipe.CSS_DOCS:
            parts.append("")
            parts.append(recipe.CSS_DOCS)
    return "\n".join(parts)


def _build_recipes_section(recipes: list) -> str:
    """Build the visual component recipes section from selected recipes."""
    if not recipes:
        return ""
    parts = ["=== VISUAL COMPONENT RECIPES ===\n"]
    for recipe in recipes:
        if hasattr(recipe, "PATTERN") and recipe.PATTERN:
            parts.append(recipe.PATTERN)
            parts.append("")
    return "\n".join(parts)


def _build_steps_section(frame: dict) -> str:
    """Build the animation steps section from frame data."""
    steps = frame.get("steps", [])
    if not steps:
        return "NO EXPLICIT STEPS — create at least 3 logical steps from the description."

    step_lines = []
    for s in steps:
        label = s.get("label", s.get("step_id", "?"))
        desc = s.get("description", "")
        dur = s.get("duration_seconds", 3)
        pause = " [PAUSE]" if s.get("pause_after") else ""
        narration = s.get("narration_spoken", "") or s.get("narration", "")
        line = f"  - Step '{label}' ({dur}s{pause}): {desc}"
        if narration:
            narr_short = narration[:120].rstrip()
            line += f'\n    Teacher says: "{narr_short}"'
        step_lines.append(line)

    return (
        "ANIMATION STEPS (create GSAP labels for each — "
        "the teacher narration tells you what must be visible):\n"
        + "\n".join(step_lines)
    )


def _build_images_section(available_images: dict[str, str] | None) -> str:
    """Build the available images section."""
    if not available_images:
        return ""
    lines = [
        "=== PRE-GENERATED IMAGES (available in __images object) ===",
        "",
        "The template provides a global `__images` object keyed by step label.",
        "To show a pre-generated image:",
        "",
        "  const img = document.createElement('img');",
        "  img.src = __images['step-label'];",
        "  img.style.cssText = 'max-width:40%; border:2px solid #3B82F6; "
        "border-radius:8px; opacity:0;';",
        "  mainZone.appendChild(img);",
        "  tl.to(img, {opacity: 1, duration: 0.8}, 'step-label');",
        "",
        "Available image labels:",
    ]
    for label in available_images:
        lines.append(f'  - __images["{label}"]')
    return "\n".join(lines)


def compose(
    frame: dict,
    available_images: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Compose system + user prompts for a browser visual frame.

    Returns:
        (system_prompt, user_prompt) ready for the LLM.
    """
    recipes = select_recipes(frame)

    # ── System prompt ──
    css_section = _build_css_section(recipes)
    system_prompt = CORE_SYSTEM.format(css_section=css_section)

    # ── User prompt ──
    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)

    steps_section = _build_steps_section(frame)
    images_section = _build_images_section(available_images)
    recipes_section = _build_recipes_section(recipes)

    user_header = CORE_USER_HEADER.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=frame.get("visual_type", "animation"),
        description=description,
        duration=frame.get("estimated_seconds", 30),
        steps_section=steps_section,
        available_images=images_section,
    )

    user_prompt = "\n\n".join(
        part for part in [user_header, recipes_section, CORE_USER_FOOTER] if part
    )

    logger.info(
        "Composed prompt: system=%d chars, user=%d chars, recipes=%s",
        len(system_prompt), len(user_prompt), [r.ID for r in recipes],
    )
    return system_prompt, user_prompt
