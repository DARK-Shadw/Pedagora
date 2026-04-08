"""Per-frame visual generator — hybrid browser HTML + Manim MP4 rendering."""

import ast
import json
import logging
import os
import re
import shutil
import subprocess
import time

from app.engine.claude_engine import ClaudeEngine
from app.agents.animation_v2.prompts import (
    build_generation_prompt, build_fix_prompt, VISUAL_GENERATION_SYSTEM,
    build_manim_generation_prompt, build_manim_fix_prompt, MANIM_GENERATION_SYSTEM,
)
from app.agents.animation_v2.template import FRAME_HTML_TEMPLATE, VIDEO_HTML_TEMPLATE
from app.agents.animation.renderer import render_manim_scene
from app.config import get_settings
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


# ══���════════════════════════════════════════════════════════
# Routing — decide browser vs Manim per frame
# ═══════════════════════════════════════════════════════════

MANIM_KEYWORDS = [
    "3d", "surface plot", "surface mesh", "particle system",
    "vector field", "camera rotation", "gaussian surface",
    "3d gaussian", "probability surface", "3d axes",
    "heatmap", "contour", "topographic",
    "phase space", "manifold", "torus", "sphere",
    "eigenvalue", "eigenvector", "matrix transformation",
    "fourier transform animation",
]

ALWAYS_BROWSER = {"interactive", "code", "blackboard", "image", "image_sequence"}


def route_frame(frame: dict) -> str:
    """Decide rendering backend: 'browser' or 'manim'."""
    visual_type = frame.get("visual_type", "animation")
    vspec = frame.get("visual_spec", {})

    # Explicit override from course planner
    hint = vspec.get("render_hint", "")
    if hint in ("manim", "browser"):
        return hint

    # Types that must be browser
    if visual_type in ALWAYS_BROWSER:
        return "browser"

    # Keyword check on description
    description = str(vspec.get("description", "")).lower()
    for kw in MANIM_KEYWORDS:
        if kw in description:
            logger.info(f"[AnimV2] {frame.get('frame_id')}: routed to manim (matched '{kw}')")
            return "manim"

    return "browser"


# ═══��════════════════════════���══════════════════════════════
# Browser path helpers (existing v2 logic)
# ══════════════��════════════════════════════════════════════

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
        stripped = line.strip()
        if stripped.startswith(("const ", "let ", "var ", "//", "function", "tl.", "gsap.", "d3.",
                                "document.", "katex.", "Prism.", "{", "}", ")", "]", "for ", "if ")):
            in_code = True
        if in_code or not stripped:
            code_lines.append(line)

    if code_lines:
        return "\n".join(code_lines).strip()

    return text


def validate_js_syntax(js_code: str) -> str | None:
    """Validate JS syntax using Node.js. Returns error message or None if valid."""
    node_path = shutil.which("node")
    if not node_path:
        logger.warning("[AnimV2] Node.js not found, skipping syntax validation")
        return None

    check_script = f"try {{ new Function({repr(js_code)}); }} catch(e) {{ process.stderr.write(e.message); process.exit(1); }}"
    try:
        result = subprocess.run(
            [node_path, "-e", check_script],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        if result.returncode != 0:
            return result.stderr.strip() or "Unknown syntax error"
        return None
    except Exception as e:
        logger.warning(f"[AnimV2] Syntax check failed to run: {e}")
        return None


def build_html(js_code: str, title: str) -> str:
    """Wrap animation JS code in the browser HTML template."""
    return FRAME_HTML_TEMPLATE.format(
        title=title,
        content_html="",
        animation_js=js_code,
    )


# ═���═════════════════════════════════════════════════════════
# Manim path helpers
# ════════════════════════��══════════════════════════════════

def extract_python(text: str) -> str | None:
    """Extract Python code from Claude's response."""
    text = text.strip()

    # Strip markdown fences
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Raw code starting with import or class
    if text.startswith(("from manim", "import ", "class ")):
        return text

    return text


def validate_manim_code(code: str) -> str | None:
    """Validate Python syntax and class structure. Returns error or None."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"

    if "class AnimationScene" not in code:
        return "Missing 'class AnimationScene' — code must define this class"

    return None


def compute_step_map(steps: list[dict]) -> dict[str, float]:
    """Compute step label → cumulative timestamp mapping for video seeking."""
    step_map = {}
    cumulative = 0.0
    for s in steps:
        label = s.get("label", s.get("step_id", f"step-{len(step_map)}"))
        step_map[label] = round(cumulative, 2)
        cumulative += s.get("duration_seconds", 3.0)
    if not step_map:
        # Default steps if none defined
        step_map = {"intro": 0, "main": 5, "conclusion": 15}
    return step_map


def build_video_html(video_url: str, title: str, steps: list[dict]) -> str:
    """Wrap a Manim MP4 URL in HTML with the same animationAPI interface."""
    step_map = compute_step_map(steps)
    return VIDEO_HTML_TEMPLATE.format(
        title=title,
        video_url=video_url,
        step_map_json=json.dumps(step_map),
    )


def _upload_manim_mp4(local_path: str, goal_id: str, lesson_id: str, frame_id: str) -> str:
    """Upload rendered MP4 to Supabase Storage and return public URL."""
    sb = get_supabase()
    storage_path = f"visuals/{goal_id}/{lesson_id}/{frame_id}.mp4"

    with open(local_path, "rb") as f:
        sb.storage.from_("animations").upload(
            storage_path, f.read(),
            file_options={"content-type": "video/mp4", "upsert": "true"},
        )

    return sb.storage.from_("animations").get_public_url(storage_path)


# ��══════════════════════════════════���═══════════════════════
# Browser generation (existing v2 flow)
# ══════��══════════════════════════════════════════════��═════

async def _generate_browser_visual(
    engine: ClaudeEngine,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
) -> dict:
    """Generate a browser-rendered HTML visual (GSAP + D3 + KaTeX)."""
    frame_id = frame.get("frame_id", "unknown")
    visual_type = frame.get("visual_type", "animation")
    is_fix = previous_error and previous_code

    if progress_fn:
        label = "Fixing" if is_fix else "Generating"
        progress_fn(f"[{frame_id}] {label} {visual_type} (browser)...")

    if is_fix:
        prompt = build_fix_prompt(frame, previous_code, previous_error)
    else:
        prompt = build_generation_prompt(frame)

    try:
        result = await engine.run(
            prompt=prompt,
            system_prompt=VISUAL_GENERATION_SYSTEM,
            timeout=600,
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

        # Validate JS syntax
        syntax_error = validate_js_syntax(js_code)
        if syntax_error:
            logger.error(f"[AnimV2] {frame_id}: Syntax error: {syntax_error}")
            if progress_fn:
                progress_fn(f"[{frame_id}] Syntax error: {syntax_error[:60]}")
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": f"JS syntax error: {syntax_error}",
                "failed_code": js_code,
                "raw_length": len(js_code),
            }

        title = frame.get("visual_spec", {}).get("description", "")[:60] or frame_id
        html = build_html(js_code, title)

        elapsed = result.get("elapsed_seconds", 0)
        logger.info(f"[AnimV2] {frame_id}: Generated {len(js_code)} chars JS -> {len(html)} chars HTML in {elapsed:.0f}s")

        if progress_fn:
            progress_fn(f"[{frame_id}] Done (browser): {len(html)} chars")

        return {
            "frame_id": frame_id,
            "visual_type": visual_type,
            "html": html,
            "html_size": len(html),
            "status": "completed",
            "elapsed_seconds": elapsed,
            "renderer": "browser",
        }

    except Exception as e:
        logger.error(f"[AnimV2] {frame_id}: Browser generation failed: {e}")
        if progress_fn:
            progress_fn(f"[{frame_id}] Failed: {str(e)[:50]}")
        return {
            "frame_id": frame_id,
            "status": "failed",
            "error": str(e),
        }


# ════════════���══════════════════════════════════════════════
# Manim generation (new path)
# ═══════════════════════════════════════════════════════════

async def _generate_manim_visual(
    engine: ClaudeEngine,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
) -> dict:
    """Generate a Manim-rendered MP4, wrapped in video HTML."""
    frame_id = frame.get("frame_id", "unknown")
    visual_type = frame.get("visual_type", "animation")
    is_fix = previous_error and previous_code

    if progress_fn:
        label = "Fixing" if is_fix else "Generating"
        progress_fn(f"[{frame_id}] {label} {visual_type} (manim)...")

    # --- Step 1: Generate Python code via Claude ---
    if is_fix:
        prompt = build_manim_fix_prompt(frame, previous_code, previous_error)
    else:
        prompt = build_manim_generation_prompt(frame)

    try:
        gen_start = time.time()
        result = await engine.run(
            prompt=prompt,
            system_prompt=MANIM_GENERATION_SYSTEM,
            timeout=600,
        )
        gen_elapsed = time.time() - gen_start

        py_code = extract_python(result["result"])
        if not py_code:
            logger.error(f"[AnimV2] {frame_id}: No Python code in response")
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": "No Python code in response",
                "raw_length": len(result["result"]),
            }

        if progress_fn:
            progress_fn(f"[{frame_id}] Code generated ({len(py_code)} chars, {gen_elapsed:.0f}s), validating...")

        # --- Step 2: Validate Python syntax + class structure ---
        code_error = validate_manim_code(py_code)
        if code_error:
            # Try auto-wrapping if it has construct() body but no class
            if "class AnimationScene" not in py_code and ("self.play" in py_code or "self.wait" in py_code):
                py_code = (
                    "from manim import *\nimport numpy as np\n\n"
                    "class AnimationScene(Scene):\n"
                    "    def construct(self):\n"
                    + "\n".join(f"        {line}" for line in py_code.split("\n"))
                )
                code_error = validate_manim_code(py_code)

            if code_error:
                logger.error(f"[AnimV2] {frame_id}: Manim code error: {code_error}")
                if progress_fn:
                    progress_fn(f"[{frame_id}] Code error: {code_error[:60]}")
                return {
                    "frame_id": frame_id,
                    "status": "failed",
                    "error": f"Manim code error: {code_error}",
                    "failed_code": py_code,
                    "raw_length": len(py_code),
                }

        # --- Step 3: Render with Manim ---
        if progress_fn:
            progress_fn(f"[{frame_id}] Rendering with Manim (1080p60)...")

        settings = get_settings()
        output_dir = os.path.join(
            settings.manim_output_dir,
            frame.get("_goal_id", "local"),
            frame.get("_lesson_id", "test"),
            frame_id,
        )

        render_start = time.time()
        mp4_path, render_error = await render_manim_scene(
            code=py_code,
            output_dir=output_dir,
            quality=settings.animation_render_quality,
            timeout=300,
        )
        render_elapsed = time.time() - render_start

        if render_error:
            logger.error(f"[AnimV2] {frame_id}: Render failed ({render_elapsed:.0f}s): {render_error[:100]}")
            if progress_fn:
                progress_fn(f"[{frame_id}] Render failed: {render_error[:60]}")
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": f"Manim render error: {render_error}",
                "failed_code": py_code,
                "raw_length": len(py_code),
            }

        if not mp4_path or not os.path.exists(mp4_path) or os.path.getsize(mp4_path) == 0:
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": "Manim render produced empty or missing MP4",
                "failed_code": py_code,
            }

        mp4_size = os.path.getsize(mp4_path)
        if progress_fn:
            progress_fn(f"[{frame_id}] Rendered {mp4_size // 1024}KB MP4 in {render_elapsed:.0f}s")

        # --- Step 4: Upload MP4 + build video HTML ---
        goal_id = frame.get("_goal_id", "")
        lesson_id = frame.get("_lesson_id", "")

        if goal_id and lesson_id:
            try:
                video_url = _upload_manim_mp4(mp4_path, goal_id, lesson_id, frame_id)
                if progress_fn:
                    progress_fn(f"[{frame_id}] MP4 uploaded to storage")
            except Exception as e:
                logger.error(f"[AnimV2] {frame_id}: MP4 upload failed: {e}")
                # Fall back to local path
                video_url = mp4_path
        else:
            # Local-only mode (testing)
            video_url = mp4_path

        title = frame.get("visual_spec", {}).get("description", "")[:60] or frame_id
        steps = frame.get("steps", [])
        html = build_video_html(video_url, title, steps)

        total_elapsed = gen_elapsed + render_elapsed
        logger.info(
            f"[AnimV2] {frame_id}: Manim render complete — "
            f"{len(py_code)} chars Python, {mp4_size // 1024}KB MP4, "
            f"{total_elapsed:.0f}s total (gen {gen_elapsed:.0f}s + render {render_elapsed:.0f}s)"
        )

        if progress_fn:
            progress_fn(f"[{frame_id}] Done (manim): {mp4_size // 1024}KB MP4")

        return {
            "frame_id": frame_id,
            "visual_type": visual_type,
            "html": html,
            "html_size": len(html),
            "mp4_size": mp4_size,
            "mp4_path": mp4_path,
            "status": "completed",
            "elapsed_seconds": total_elapsed,
            "renderer": "manim",
        }

    except Exception as e:
        logger.error(f"[AnimV2] {frame_id}: Manim generation failed: {e}")
        if progress_fn:
            progress_fn(f"[{frame_id}] Failed: {str(e)[:50]}")
        return {
            "frame_id": frame_id,
            "status": "failed",
            "error": str(e),
        }


# ��════════════════════════════��═════════════════════════════
# Main entry point — routes to browser or manim
# ══════���══════════════��═════════════════════════════════════

async def generate_frame_visual(
    engine: ClaudeEngine,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
) -> dict:
    """Generate a self-contained HTML visual for one VisualFrame.

    Routes to browser (GSAP/D3) or Manim (MP4) based on frame complexity.
    Both paths return the same dict shape with 'html' containing the full page.
    """
    renderer = route_frame(frame)

    if renderer == "manim":
        return await _generate_manim_visual(
            engine, frame, progress_fn, previous_error, previous_code,
        )
    else:
        return await _generate_browser_visual(
            engine, frame, progress_fn, previous_error, previous_code,
        )
