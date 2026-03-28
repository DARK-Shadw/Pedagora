"""Per-frame visual generator — creates self-contained HTML from VisualFrame specs."""

import json
import logging
import re

from app.engine.claude_engine import ClaudeEngine
from app.agents.animation_v2.prompts import build_generation_prompt, VISUAL_GENERATION_SYSTEM
from app.agents.animation_v2.template import FRAME_HTML_TEMPLATE

logger = logging.getLogger(__name__)


def extract_js(text: str) -> str | None:
    """Extract JavaScript code from Claude's response."""
    text = text.strip()

    # Strip markdown fences if present
    match = re.search(r"```(?:javascript|js)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If no fences, assume the whole thing is JS
    # But skip any leading explanation text
    lines = text.split("\n")
    code_lines = []
    in_code = False
    for line in lines:
        # Heuristic: code lines start with const, let, var, //, function, tl., gsap., d3., or are empty
        stripped = line.strip()
        if stripped.startswith(("const ", "let ", "var ", "//", "function", "tl.", "gsap.", "d3.",
                                "document.", "katex.", "Prism.", "{", "}", ")", "]", "for ", "if ")):
            in_code = True
        if in_code or not stripped:
            code_lines.append(line)

    if code_lines:
        return "\n".join(code_lines).strip()

    return text  # Return as-is, hope for the best


def build_html(js_code: str, title: str) -> str:
    """Wrap animation JS code in the HTML template."""
    return FRAME_HTML_TEMPLATE.format(
        title=title,
        content_html="",  # JS will create DOM elements dynamically
        animation_js=js_code,
    )


async def generate_frame_visual(
    engine: ClaudeEngine,
    frame: dict,
    progress_fn=None,
) -> dict:
    """Generate a self-contained HTML visual for one VisualFrame."""
    frame_id = frame.get("frame_id", "unknown")
    visual_type = frame.get("visual_type", "animation")

    if progress_fn:
        progress_fn(f"[{frame_id}] Generating {visual_type}...")

    prompt = build_generation_prompt(frame)

    try:
        result = await engine.run(
            prompt=prompt,
            system_prompt=VISUAL_GENERATION_SYSTEM,
            timeout=600,  # 10 min per frame — complex HTML generation
        )

        js_code = extract_js(result["result"])
        if not js_code:
            logger.error(f"[AnimV2] {frame_id}: No JS code found in response")
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": "No JS code in response",
                "raw_length": len(result["result"]),
            }

        # Wrap in HTML template (template handles GSAP, API, dark theme)
        title = frame.get("visual_spec", {}).get("description", "")[:60] or frame_id
        html = build_html(js_code, title)

        elapsed = result.get("elapsed_seconds", 0)
        logger.info(f"[AnimV2] {frame_id}: Generated {len(js_code)} chars JS -> {len(html)} chars HTML in {elapsed:.0f}s")

        if progress_fn:
            progress_fn(f"[{frame_id}] Done: {len(html)} chars")

        return {
            "frame_id": frame_id,
            "visual_type": visual_type,
            "html": html,
            "html_size": len(html),
            "status": "completed",
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        logger.error(f"[AnimV2] {frame_id}: Failed: {e}")
        if progress_fn:
            progress_fn(f"[{frame_id}] Failed: {str(e)[:50]}")
        return {
            "frame_id": frame_id,
            "status": "failed",
            "error": str(e),
        }
