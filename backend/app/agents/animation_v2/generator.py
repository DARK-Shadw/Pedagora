"""Per-frame visual generator — hybrid browser HTML + Manim MP4 rendering.

PIPELINE STAGE 3, inner loop (see docs/architecture-flow.svg)

Each frame goes through one of two rendering paths:

  BROWSER PATH (most frames):
    LLM → GSAP/JS code → wrap in HTML template → Playwright validation
    Output: self-contained HTML file with GSAP timeline + labeled steps

  MANIM PATH (complex math animations):
    LLM → Python Manim code → subprocess render → MP4 → wrap in HTML video player
    Output: HTML page embedding the rendered MP4

Both paths retry up to 3 attempts. On validation failure, the runtime
error is fed back into the LLM as a "fix prompt" for the next attempt.

Uses GeminiClient (multi-key pool with structured JSON output) for code
generation. Falls back to Pollinations deepseek when pool is exhausted.
"""

import ast
import asyncio
import base64
import json
import logging
import os
import time

from app.agents.animation_v2.gemini_client import GeminiClient, GeminiPoolExhausted
from app.agents.animation_v2.narration import generate_frame_narration
from app.agents.animation_v2.prompt_composer import compose as compose_prompt
from app.agents.animation_v2.prompts import (
    build_fix_prompt, VISUAL_GENERATION_SYSTEM,
    build_manim_generation_prompt, build_manim_fix_prompt, MANIM_GENERATION_SYSTEM,
)
from app.agents.animation_v2.template import FRAME_HTML_TEMPLATE, VIDEO_HTML_TEMPLATE
from app.agents.animation_v2.validator import validate_animation_runtime
from app.agents.animation.renderer import render_manim_scene
from app.agents.critic.visual_critic import review_animation_screenshots
from app.config import get_settings
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

MAX_BROWSER_RETRY_ATTEMPTS = 3  # initial gen + 2 retries
MAX_MANIM_RETRY_ATTEMPTS = 3    # initial gen + 2 retries (mirror of browser path)

# When using NvidiaClient, model is set internally (moonshotai/kimi-k2.6).
# This constant is only used as a Gemini override — NvidiaClient ignores it.
MANIM_MODEL = "gemini-2.5-flash"

# Pollinations deepseek as unlimited fallback when Gemini pool is exhausted.
# 283 lines, correct ThreeDScene usage, renders first-try in testing.
FALLBACK_MODEL = "deepseek"
FALLBACK_API_URL = "https://gen.pollinations.ai/v1/chat/completions"


async def _generate_code_via_pollinations(
    *,
    prompt: str,
    system_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> tuple[str, dict]:
    """Fallback code generation via Pollinations deepseek.

    Called only when all Gemini API keys are exhausted. Same interface as
    GeminiClient.generate_code: returns (code, meta).

    Raises RuntimeError on empty/unparseable responses.
    """
    import httpx

    settings = get_settings()
    api_key = settings.pollinations_api_key
    if not api_key:
        raise RuntimeError("No pollinations_api_key configured for fallback")

    payload = {
        "model": FALLBACK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    t0 = time.time()
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            FALLBACK_API_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp.raise_for_status()

    elapsed = time.time() - t0
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    # Extract code — model may return JSON {"code": "..."} or markdown-fenced Python
    code = None
    try:
        parsed = json.loads(content)
        code = (parsed.get("code") or "").strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    if not code:
        code = extract_python(content)
    if not code:
        code = content.strip()

    if not code or "class AnimationScene" not in code:
        raise RuntimeError(
            f"Pollinations {FALLBACK_MODEL} returned unusable code "
            f"({len(code)} chars): {code[:200]!r}"
        )

    meta = {
        "elapsed_seconds": round(elapsed, 2),
        "model": f"pollinations:{FALLBACK_MODEL}",
        "key_index": "fallback",
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
    }
    logger.info(
        f"[AnimV2] Pollinations fallback OK in {elapsed:.1f}s "
        f"({meta['tokens_in']}->{meta['tokens_out']} tok, {len(code)} chars)"
    )
    return code, meta


# ════════════════════════════════════════════════════════════
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

def fix_katex_escaping(js_code: str) -> str:
    r"""Fix single-backslash LaTeX commands to double-backslash in JS strings.

    Gemini Flash Lite consistently generates `\frac`, `\sum`, `\approx` etc.
    in katex.render() strings.  In JavaScript, `\f` is form-feed, `\t` is tab,
    and other `\X` sequences silently drop the backslash — destroying the
    LaTeX command.  KaTeX needs a literal `\` which requires `\\` in JS.

    This function adds the second backslash for all known LaTeX commands,
    skipping any that are already correctly double-escaped.
    """
    # Longest-first to avoid partial matches (e.g. "sum" before "subset")
    LATEX_CMDS = sorted([
        "frac", "dfrac", "tfrac", "sum", "prod", "int", "iint", "oint",
        "Omega", "omega", "mu", "sigma", "pi", "theta", "alpha", "beta",
        "gamma", "delta", "epsilon", "varepsilon", "lambda", "Lambda",
        "phi", "Phi", "psi", "Psi", "chi", "rho", "tau", "eta", "zeta",
        "kappa", "nu", "xi", "Delta", "Gamma", "Sigma", "Theta", "Pi",
        "to", "cdot", "cdots", "ldots", "times", "div",
        "approx", "sim", "equiv", "propto", "neq", "ne",
        "le", "leq", "ge", "geq", "ll", "gg",
        "in", "notin", "subset", "supset", "subseteq", "supseteq",
        "cup", "cap", "vee", "wedge", "neg",
        "forall", "exists", "nabla", "partial", "infty",
        "mathbb", "mathbf", "mathcal", "mathrm", "mathit",
        "text", "textbf", "textit", "operatorname",
        "color", "textcolor", "boxed",
        "sqrt", "root", "overline", "underline", "hat", "bar", "vec", "dot",
        "left", "right", "bigl", "bigr", "Big", "big",
        "begin", "end", "binom", "choose",
        "lim", "log", "ln", "sin", "cos", "tan", "exp", "max", "min",
        "pm", "mp",
        # LaTeX special characters (\ + symbol)
        "%", "#", "&",
    ], key=len, reverse=True)

    import re as _re
    for cmd in LATEX_CMDS:
        # Match: one backslash + command + word boundary (non-alpha or end)
        # Skip: already two backslashes (negative lookbehind)
        pattern = r"(?<!\\)\\(" + _re.escape(cmd) + r")(?=[^a-zA-Z]|$)"
        js_code = _re.sub(pattern, r"\\\\\1", js_code)
    return js_code


def fix_gsap_targets(js_code: str) -> str:
    """Wrap GSAP tween targets with _t() to convert D3 selections to DOM elements.

    Only activates when D3 selections are detected (d3.select, .append, .selectAll).
    Without D3 usage, wrapping is unnecessary and can interfere with GSAP.
    """
    if 'd3.select' not in js_code and '.append(' not in js_code:
        return js_code
    if 'document.createElement' in js_code and 'd3.select' not in js_code:
        return js_code

    import re as _re

    PATTERN = _re.compile(r'tl\.(to|from|fromTo)\(')

    def _find_first_arg_end(code: str, start: int) -> int:
        """Return index of the comma that ends the first argument, or -1."""
        depth_paren = 0
        depth_bracket = 0
        depth_brace = 0
        i = start
        while i < len(code):
            ch = code[i]
            if ch == '(':
                depth_paren += 1
            elif ch == ')':
                if depth_paren == 0:
                    return -1
                depth_paren -= 1
            elif ch == '[':
                depth_bracket += 1
            elif ch == ']':
                depth_bracket -= 1
            elif ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == ',' and depth_paren == 0 and depth_bracket == 0 and depth_brace == 0:
                return i
            i += 1
        return -1

    result = []
    last_end = 0
    for m in PATTERN.finditer(js_code):
        arg_start = m.end()
        arg_text_before = js_code[arg_start:arg_start + 3]
        if arg_text_before.startswith('_t(') or arg_text_before.startswith('['):
            continue

        comma_idx = _find_first_arg_end(js_code, arg_start)
        if comma_idx == -1:
            continue

        target = js_code[arg_start:comma_idx]
        result.append(js_code[last_end:arg_start])
        result.append(f'_t({target})')
        last_end = comma_idx

    result.append(js_code[last_end:])
    return ''.join(result)


def fix_svg_d_in_tweens(js_code: str) -> str:
    """Move attr:{d:...} out of GSAP tweens — GSAP can't interpolate path strings.

    When Gemini puts attr:{d: somePathData} inside a tl.to() call, the path
    never renders.  This extracts the d value and pre-sets it on the element
    by injecting a .attr('d', ...) call before the tween.

    Since this is complex to do perfectly with regex, we take a simpler approach:
    strip `attr: {d: ...}` from GSAP tweens entirely.  The prompt already tells
    Gemini to set d at creation time, so this is a safety net that prevents
    the broken pattern from silently failing.
    """
    import re as _re
    # Remove ", attr: {d: ...}" or "attr: {d: ...}, " from GSAP tween objects
    # This handles the common pattern: {opacity: 0.4, duration: 1, attr: {d: expr}}
    js_code = _re.sub(r',\s*attr\s*:\s*\{d\s*:[^}]+\}', '', js_code)
    js_code = _re.sub(r'attr\s*:\s*\{d\s*:[^}]+\}\s*,\s*', '', js_code)
    return js_code


def build_html(
    js_code: str,
    title: str,
    image_data: dict[str, str] | None = None,
) -> str:
    """Wrap animation JS code in the browser HTML template.

    Args:
        image_data: Optional dict of step_label → base64 data URL for
            pre-generated images. Injected as `__images` JS constant.
    """
    js_code = fix_katex_escaping(js_code)
    js_code = fix_gsap_targets(js_code)
    return FRAME_HTML_TEMPLATE.format(
        title=title,
        content_html="",
        animation_js=js_code,
        image_data=json.dumps(image_data or {}),
    )


# ═���═════════════════════════════════════════════════════════
# Manim path helpers
# ════════════════════════��══════════════════════════════════

def extract_python(text: str) -> str | None:
    """Return raw Python from the generator response.

    Gemini's structured output returns bare code in the `code` field, but we
    still strip whitespace and any stray markdown fences as a cheap safety net.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        # Strip leading fence line ("```python\n" or "```\n")
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def validate_manim_code(code: str) -> str | None:
    """Validate Python syntax and class structure. Returns error or None."""
    # Defensive check: Gemini sometimes collapses the entire scene onto a
    # single line with semicolons on retry. That produces a cryptic
    # "cannot use name as import target" error from Python's parser, which
    # the fix loop can't understand. Catch it up front with a clear message
    # so the retry prompt can actually help.
    stripped = code.strip()
    line_count = stripped.count("\n") + 1
    if line_count <= 3 and "class AnimationScene" in stripped and ";" in stripped:
        return (
            "Code is collapsed onto 1-3 lines with semicolons. Python cannot "
            "parse `class X: def y():` on a single line. Rewrite with real "
            "newlines — one statement per line, 4-space indentation, NO "
            "semicolons between statements."
        )

    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"

    if "class AnimationScene" not in code:
        return "Missing 'class AnimationScene' — code must define this class"

    return None


def fix_manim_api_errors(code: str) -> str:
    """Fix common Manim API mistakes that Gemini produces.

    Known patterns:
    1. axes.n2p(x) — Axes uses c2p(), not n2p() (which is NumberLine-only).
    2. .get_x()/.get_y()/.get_z() on c2p() results — returns numpy array, not Point3D.
    3. .to_edge(DOWN).shift(DOWN*X) — pushes mobjects off-screen.
    4. Custom rate_func lambdas — always broken, replace with smooth.
    """
    import re as _re

    # 1. axes.n2p(expr) → axes.c2p(expr, 0)
    # Only target Axes-like variable names; NumberLine vars (nl, number_line) are valid
    code = _re.sub(
        r'(\b(?:axes|hist_axes|ax|plot_axes|axes_?\d*)\b)\.n2p\(([^)]+)\)',
        r'\1.c2p(\2, 0)',
        code,
    )

    # 2. .get_x() → [0], .get_y() → [1], .get_z() → [2] on c2p results
    code = _re.sub(r'\.c2p\(([^)]+)\)\.get_x\(\)', r'.c2p(\1)[0]', code)
    code = _re.sub(r'\.c2p\(([^)]+)\)\.get_y\(\)', r'.c2p(\1)[1]', code)
    code = _re.sub(r'\.c2p\(([^)]+)\)\.get_z\(\)', r'.c2p(\1)[2]', code)

    # 3. .to_edge(DOWN).shift(DOWN*...) → .to_edge(DOWN)  (strip the redundant shift)
    #    Same for UP direction
    code = _re.sub(r'\.to_edge\(DOWN\)\s*\.shift\(DOWN\s*\*[^)]+\)', '.to_edge(DOWN)', code)
    code = _re.sub(r'\.to_edge\(UP\)\s*\.shift\(UP\s*\*[^)]+\)', '.to_edge(UP)', code)

    # 4. rate_func=lambda ... → rate_func=smooth
    #    Gemini's custom lambdas composing smooth/there_and_back always break at boundaries.
    #    The lambda spans to end-of-line (Manim kwargs are one per line).
    code = _re.sub(r'rate_func\s*=\s*lambda\b[^\n]*', 'rate_func=smooth', code)

    return code


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

async def _generate_browser_visual_once(
    gemini: GeminiClient,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
    image_data: dict[str, str] | None = None,
) -> dict:
    """Generate a browser-rendered HTML visual (GSAP + D3 + KaTeX) via Gemini."""
    frame_id = frame.get("frame_id", "unknown")
    visual_type = frame.get("visual_type", "animation")
    is_fix = bool(previous_error and previous_code)

    if progress_fn:
        label = "Fixing" if is_fix else "Generating"
        progress_fn(f"[{frame_id}] {label} {visual_type} (browser)...")

    if is_fix:
        prompt = build_fix_prompt(frame, previous_code, previous_error)
        system_prompt = VISUAL_GENERATION_SYSTEM
    else:
        system_prompt, prompt = compose_prompt(frame, available_images=image_data)

    try:
        js_code, meta = await gemini.generate_code(
            prompt=prompt,
            system_prompt=system_prompt,
        )
        js_code = (js_code or "").strip()

        if not js_code:
            logger.error(f"[AnimV2] {frame_id}: Gemini returned empty JS code")
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": "Gemini returned empty JS code",
            }

        title = frame.get("visual_spec", {}).get("description", "")[:60] or frame_id
        html = build_html(js_code, title, image_data=image_data)

        elapsed = meta.get("elapsed_seconds", 0)
        logger.info(
            f"[AnimV2] {frame_id}: Generated {len(js_code)} chars JS -> "
            f"{len(html)} chars HTML in {elapsed:.1f}s (key#{meta.get('key_index')})"
        )

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
            "key_index": meta.get("key_index"),
            "tokens_in": meta.get("tokens_in"),
            "tokens_out": meta.get("tokens_out"),
        }

    except GeminiPoolExhausted as e:
        logger.error(
            f"[AnimV2] {frame_id}: Gemini pool exhausted (browser): {e}",
            exc_info=True,
        )
        if progress_fn:
            progress_fn(f"[{frame_id}] Pool exhausted")
        return {
            "frame_id": frame_id,
            "status": "failed",
            "error": f"Gemini pool exhausted: {e}",
        }
    except Exception as e:
        logger.error(
            f"[AnimV2] {frame_id}: Browser generation crashed: {e}",
            exc_info=True,
        )
        if progress_fn:
            progress_fn(f"[{frame_id}] Failed: {str(e)[:50]}")
        return {
            "frame_id": frame_id,
            "status": "failed",
            "error": f"Browser generation crashed: {e}",
        }


# ════════════════════════════════════════════════════════════
# Manim image pre-generation (Pollinations)
# ════════════════════════════════════════════════════════════

IMAGE_STEP_KEYWORDS = [
    "generated image", "sample image", "example image", "real image",
    "generated output", "model output", "generated sample",
    "noise to image", "noisy image", "denoising",
    "show image", "display image", "resulting image",
    "diagram of", "illustration of", "picture of",
    "neural network output", "network generates",
]


async def _pregenerate_step_images(
    frame: dict,
    progress_fn=None,
) -> dict[str, str]:
    """Scan step descriptions and generate images via Pollinations for those that need them.

    Returns a dict mapping step_label -> absolute image path.
    Empty dict if no steps need images or generation fails.
    """
    from app.services.image_gen import generate_image

    steps = frame.get("steps", [])
    if not steps:
        return {}

    frame_id = frame.get("frame_id", "unknown")
    frame_desc = frame.get("visual_spec", {}).get("description", "")
    settings = get_settings()

    # Determine output dir for images (next to where Manim renders)
    images_dir = os.path.join(
        settings.manim_output_dir,
        frame.get("_goal_id", "local"),
        frame.get("_lesson_id", "test"),
        frame_id,
        "images",
    )

    generated: dict[str, str] = {}

    for step in steps:
        desc = str(step.get("description", "")).lower()
        label = step.get("label", step.get("step_id", "unknown"))

        if not any(kw in desc for kw in IMAGE_STEP_KEYWORDS):
            continue

        # Build an image prompt from step + frame context
        step_desc = step.get("description", "")
        img_prompt = (
            f"Educational illustration for math/science lesson: {step_desc}. "
            f"Context: {frame_desc[:200]}. "
            f"Clean, professional, dark background (#0d1117), no text overlays, "
            f"suitable for embedding in an animated presentation."
        )

        if progress_fn:
            progress_fn(f"[{frame_id}] Generating image for step '{label}'...")

        path = await generate_image(
            img_prompt,
            output_dir=images_dir,
            filename=f"{label}.jpg",
            width=800,
            height=600,
        )

        if path:
            # Use absolute path with forward slashes for Manim compatibility
            abs_path = os.path.abspath(path).replace("\\", "/")
            generated[label] = abs_path
            logger.info(f"[AnimV2] {frame_id}: Pre-generated image for '{label}': {abs_path}")
            if progress_fn:
                progress_fn(f"[{frame_id}] Image ready for step '{label}'")
        else:
            logger.warning(f"[AnimV2] {frame_id}: Image generation failed for step '{label}'")

    if generated:
        logger.info(f"[AnimV2] {frame_id}: Pre-generated {len(generated)} image(s)")

    return generated


def _images_to_base64(image_paths: dict[str, str]) -> dict[str, str]:
    """Convert step_label → file path dict to step_label → base64 data URL dict."""
    result: dict[str, str] = {}
    for label, path in image_paths.items():
        try:
            with open(path, "rb") as f:
                raw = f.read()
            ext = os.path.splitext(path)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            b64 = base64.b64encode(raw).decode("ascii")
            result[label] = f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.warning(f"[AnimV2] Failed to encode image {path}: {e}")
    return result


# ════════════════════════════════════════════════════════════
# Manim generation (code gen + render)
# ════════════════════════════════════════════════════════════

async def _generate_manim_once(
    gemini: GeminiClient,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
    available_images: dict[str, str] | None = None,
) -> dict:
    """One attempt at generating + rendering a Manim visual (no retry).

    Returns a dict with status=completed (html, mp4_size, ...) or status=failed
    (error, failed_code). The caller is responsible for retry.
    """
    frame_id = frame.get("frame_id", "unknown")
    visual_type = frame.get("visual_type", "animation")
    is_fix = bool(previous_error and previous_code)

    if progress_fn:
        label = "Fixing" if is_fix else "Generating"
        progress_fn(f"[{frame_id}] {label} {visual_type} (manim)...")

    # --- Step 1: Generate Python code via Gemini ---
    if is_fix:
        prompt = build_manim_fix_prompt(frame, previous_code, previous_error)
    else:
        prompt = build_manim_generation_prompt(frame, available_images=available_images)

    try:
        py_code_raw, meta = await gemini.generate_code(
            prompt=prompt,
            system_prompt=MANIM_GENERATION_SYSTEM,
            model=MANIM_MODEL,
        )
        gen_elapsed = meta.get("elapsed_seconds", 0.0)
        py_code = extract_python(py_code_raw)
        if py_code:
            py_code = fix_manim_api_errors(py_code)
        if not py_code:
            # Dump the raw response so we can see what Gemini actually returned
            # (whitespace-only? just a fence? a JSON envelope that escaped the
            # structured-output parser?).
            logger.error(
                f"[AnimV2] {frame_id}: Gemini returned empty Python code.\n"
                f"---- RAW GEMINI RESPONSE (first 1000 chars) ----\n"
                f"{(py_code_raw or '')[:1000]}\n"
                f"---- END RAW RESPONSE ----"
            )
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": "Gemini returned empty Python code",
            }

        # Dump the generated code up-front so we can see EXACTLY what we'll
        # validate / render — cheap to log and invaluable when things break.
        logger.info(
            f"[AnimV2] {frame_id}: Gemini generated {len(py_code)} chars Python "
            f"({gen_elapsed:.1f}s, key#{meta.get('key_index')})\n"
            f"---- GENERATED PYTHON (first 2000 chars) ----\n"
            f"{py_code[:2000]}\n"
            f"---- END GENERATED PYTHON ----"
        )

        if progress_fn:
            progress_fn(
                f"[{frame_id}] Code generated ({len(py_code)} chars, {gen_elapsed:.1f}s, "
                f"key#{meta.get('key_index')}), validating..."
            )

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
                # Full code dump on syntax failure so we can see what Gemini
                # actually produced (and line 1, which is where the error lives).
                logger.error(
                    f"[AnimV2] {frame_id}: Manim code error: {code_error}\n"
                    f"---- FAILED PYTHON (full) ----\n{py_code}\n"
                    f"---- END FAILED PYTHON ----"
                )
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
        settings = get_settings()
        renderer_label = "OpenGL" if settings.animation_use_opengl else "Cairo"
        if progress_fn:
            progress_fn(
                f"[{frame_id}] Rendering with Manim ({renderer_label}, 1080p60)..."
            )
        output_dir = os.path.join(
            settings.manim_output_dir,
            frame.get("_goal_id", "local"),
            frame.get("_lesson_id", "test"),
            frame_id,
        )

        render_start = time.time()

        def _on_render_progress(msg: str):
            logger.info(f"[AnimV2] [{frame_id}] {msg}")
            if progress_fn:
                progress_fn(f"[{frame_id}] {msg}")

        mp4_path, render_error = await render_manim_scene(
            code=py_code,
            output_dir=output_dir,
            quality=settings.animation_render_quality,
            timeout=1800,
            use_opengl=settings.animation_use_opengl,
            progress_callback=_on_render_progress,
        )
        render_elapsed = time.time() - render_start

        if render_error:
            # Full render stderr AND the Python that produced it. The code is
            # the most important piece for diagnosing render timeouts
            # (infinite self.wait, runaway run_time, bad loop, etc.).
            logger.error(
                f"[AnimV2] {frame_id}: Manim render failed after {render_elapsed:.0f}s\n"
                f"---- FULL RENDER ERROR ----\n{render_error}\n"
                f"---- END RENDER ERROR ----\n"
                f"---- PYTHON THAT FAILED TO RENDER (full) ----\n{py_code}\n"
                f"---- END FAILED PYTHON ----"
            )
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
            f"{total_elapsed:.0f}s total (gen {gen_elapsed:.1f}s + render {render_elapsed:.0f}s)"
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
            "key_index": meta.get("key_index"),
            "tokens_in": meta.get("tokens_in"),
            "tokens_out": meta.get("tokens_out"),
        }

    except GeminiPoolExhausted as e:
        # --- Fallback: Pollinations deepseek (unlimited) ---
        logger.warning(
            f"[AnimV2] {frame_id}: Gemini pool exhausted, falling back to "
            f"Pollinations {FALLBACK_MODEL}: {e}"
        )
        if progress_fn:
            progress_fn(
                f"[{frame_id}] Gemini exhausted, switching to {FALLBACK_MODEL}..."
            )
        try:
            py_code_raw, meta = await _generate_code_via_pollinations(
                prompt=prompt,
                system_prompt=MANIM_GENERATION_SYSTEM,
            )
            gen_elapsed = meta.get("elapsed_seconds", 0.0)
            py_code = fix_manim_api_errors(py_code_raw)

            if progress_fn:
                progress_fn(
                    f"[{frame_id}] Fallback generated {len(py_code)} chars "
                    f"({gen_elapsed:.1f}s), validating..."
                )

            # Continue with the same validate → render → upload pipeline.
            # (Falls through to the validation/render code below via a
            #  recursive call so we don't duplicate 200 lines of render logic.)
        except Exception as fb_err:
            logger.error(
                f"[AnimV2] {frame_id}: Pollinations fallback also failed: {fb_err}"
            )
            if progress_fn:
                progress_fn(f"[{frame_id}] Both Gemini and fallback failed")
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": f"Gemini exhausted + fallback failed: {fb_err}",
            }

        # Validate + render the fallback code using the same pipeline
        code_error = validate_manim_code(py_code)
        if code_error:
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": f"Fallback code error: {code_error}",
                "failed_code": py_code,
            }

        # Render with Manim (same logic as the primary path)
        settings = get_settings()
        output_dir = os.path.join(
            settings.manim_output_dir,
            frame.get("_goal_id", "local"),
            frame.get("_lesson_id", "test"),
            frame_id,
        )
        if progress_fn:
            progress_fn(f"[{frame_id}] Rendering fallback code with Manim...")

        def _on_fallback_progress(msg: str):
            logger.info(f"[AnimV2] [{frame_id}] fallback: {msg}")
            if progress_fn:
                progress_fn(f"[{frame_id}] fallback: {msg}")

        mp4_path, render_error = await render_manim_scene(
            code=py_code,
            output_dir=output_dir,
            quality=settings.animation_render_quality,
            timeout=1800,
            use_opengl=settings.animation_use_opengl,
            progress_callback=_on_fallback_progress,
        )

        if render_error:
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": f"Fallback render error: {render_error}",
                "failed_code": py_code,
            }

        if not mp4_path or not os.path.exists(mp4_path) or os.path.getsize(mp4_path) == 0:
            return {
                "frame_id": frame_id,
                "status": "failed",
                "error": "Fallback render produced empty MP4",
                "failed_code": py_code,
            }

        mp4_size = os.path.getsize(mp4_path)
        goal_id = frame.get("_goal_id", "")
        lesson_id = frame.get("_lesson_id", "")
        if goal_id and lesson_id:
            try:
                video_url = _upload_manim_mp4(mp4_path, goal_id, lesson_id, frame_id)
            except Exception:
                video_url = mp4_path
        else:
            video_url = mp4_path

        title = frame.get("visual_spec", {}).get("description", "")[:60] or frame_id
        steps = frame.get("steps", [])
        html = build_video_html(video_url, title, steps)

        logger.info(
            f"[AnimV2] {frame_id}: Fallback render complete — "
            f"{len(py_code)} chars, {mp4_size // 1024}KB MP4 via {FALLBACK_MODEL}"
        )
        return {
            "frame_id": frame_id,
            "visual_type": visual_type,
            "html": html,
            "html_size": len(html),
            "mp4_size": mp4_size,
            "mp4_path": mp4_path,
            "status": "completed",
            "elapsed_seconds": gen_elapsed,
            "renderer": "manim",
            "key_index": "fallback",
            "tokens_in": meta.get("tokens_in"),
            "tokens_out": meta.get("tokens_out"),
        }

    except Exception as e:
        logger.error(
            f"[AnimV2] {frame_id}: Manim generation crashed: {e}",
            exc_info=True,
        )
        if progress_fn:
            progress_fn(f"[{frame_id}] Failed: {str(e)[:50]}")
        return {
            "frame_id": frame_id,
            "status": "failed",
            "error": f"Manim generation crashed: {e}",
        }


async def _generate_manim_visual(
    gemini: GeminiClient,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
) -> dict:
    """Manim generation wrapper with inner retry loop.

    Each attempt calls Gemini, renders with Manim, and — on any failure —
    feeds the error + failing code back into the next attempt's fix prompt.
    Mirrors the browser retry loop in _generate_browser_visual.
    """
    frame_id = frame.get("frame_id", "unknown")

    # --- Pre-generate images for steps that need them ---
    available_images = await _pregenerate_step_images(frame, progress_fn)

    # Start narration gen early — it runs in parallel with the much-longer
    # Manim render, so it's ready by the time any attempt succeeds.
    narration_task = asyncio.create_task(generate_frame_narration(gemini, frame))

    last_result: dict = {}
    last_error: str | None = previous_error
    last_code: str | None = previous_code

    for attempt in range(1, MAX_MANIM_RETRY_ATTEMPTS + 1):
        is_fix = bool(last_error and last_code)
        logger.info(
            f"[AnimV2] {frame_id} manim attempt {attempt}/{MAX_MANIM_RETRY_ATTEMPTS} "
            f"starting (fix={is_fix}"
            + (f", prev_error={last_error[:120]}" if is_fix else "")
            + ")"
        )
        if progress_fn:
            progress_fn(f"[{frame_id}] manim attempt {attempt}/{MAX_MANIM_RETRY_ATTEMPTS}")

        result = await _generate_manim_once(
            gemini,
            frame,
            progress_fn=progress_fn,
            previous_error=last_error,
            previous_code=last_code,
            available_images=available_images or None,
        )
        last_result = result

        if result.get("status") == "completed":
            # Collect narration (should be long done — render took minutes)
            try:
                narrations = await asyncio.wait_for(narration_task, timeout=90.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
                logger.warning(f"[AnimV2] {frame_id} manim narration failed: {e}")
                narrations = None
            if narrations:
                result["narration_texts"] = narrations
                logger.info(
                    f"[AnimV2] {frame_id} manim narration OK: "
                    f"{len(narrations)} steps"
                )
            return result

        last_error = result.get("error") or "manim generation failed"
        last_code = result.get("failed_code") or last_code
        logger.warning(
            f"[AnimV2] {frame_id} manim FAIL attempt "
            f"{attempt}/{MAX_MANIM_RETRY_ATTEMPTS}\n"
            f"---- FULL ATTEMPT ERROR ----\n{last_error}\n"
            f"---- END ATTEMPT ERROR ----"
        )

    narration_task.cancel()
    last_result["status"] = "failed"
    last_result.setdefault("error", last_error or "manim generation failed")
    return last_result


# ��════════════════════════════��═════════════════════════════
# Main entry point — routes to browser or manim
# ══════���══════════════��═════════════════════════════════════

async def generate_frame_visual(
    gemini: GeminiClient,
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
            gemini, frame, progress_fn, previous_error, previous_code,
        )
    else:
        return await _generate_browser_visual(
            gemini, frame, progress_fn, previous_error, previous_code,
        )


# ═══════════════════════════════════════════════════════════
# Browser generation wrapper — runtime validator + visual critic loop
# ═══════════════════════════════════════════════════════════

async def _generate_browser_visual(
    gemini: GeminiClient,
    frame: dict,
    progress_fn=None,
    previous_error: str | None = None,
    previous_code: str | None = None,
) -> dict:
    """Generate browser HTML, then validate it in a real browser before
    accepting it.

    Pipeline per attempt:
      1. Call _generate_browser_visual_once to produce HTML.
      2. Run Playwright validator: pageerror, animationAPI presence,
         GSAP labels match the planner's expected step labels, screenshots
         per label.
      3. If validator fails → feed `validator.blocking` back as the next
         attempt's `previous_error`. Up to MAX_BROWSER_RETRY_ATTEMPTS total.
      4. On the last passing attempt, run the visual critic on the
         screenshots; soft fail (advisory only) — don't block on taste-level
         issues at this layer.
    """
    frame_id = frame.get("frame_id", "unknown")
    expected_labels = [
        s.get("label", "") for s in (frame.get("steps") or [])
        if isinstance(s, dict) and s.get("label")
    ]

    # --- Pre-generate images for steps that need them ---
    raw_images = await _pregenerate_step_images(frame, progress_fn)
    image_b64 = _images_to_base64(raw_images) if raw_images else {}

    last_result: dict = {}
    last_error: str | None = previous_error
    last_code: str | None = previous_code

    for attempt in range(1, MAX_BROWSER_RETRY_ATTEMPTS + 1):
        is_fix = bool(last_error and last_code)
        logger.info(
            f"[AnimV2] {frame_id} browser attempt {attempt}/{MAX_BROWSER_RETRY_ATTEMPTS} "
            f"starting (fix={is_fix}"
            + (f", prev_error={last_error[:120]}" if is_fix else "")
            + ")"
        )
        if progress_fn:
            progress_fn(f"[{frame_id}] browser attempt {attempt}/{MAX_BROWSER_RETRY_ATTEMPTS}")

        result = await _generate_browser_visual_once(
            gemini,
            frame,
            progress_fn=progress_fn,
            previous_error=last_error,
            previous_code=last_code,
            image_data=image_b64 or None,
        )
        last_result = result

        if result.get("status") != "completed":
            # Generation itself failed (no JS / syntax error) — feed back to next attempt
            last_error = result.get("error") or "generation failed"
            last_code = result.get("failed_code")
            continue

        html = result.get("html", "")
        if not html:
            last_error = "empty HTML"
            continue

        # ── Runtime validation first ──
        if progress_fn:
            progress_fn(f"[{frame_id}] validating in browser...")
        runtime = await validate_animation_runtime(
            html=html,
            expected_labels=expected_labels,
            capture_screenshots=True,
        )
        result["runtime"] = runtime.to_dict()

        if not runtime.passed:
            last_error = "; ".join(runtime.blocking)[:600] or "runtime validation failed"
            last_code = html
            full_blocking = "\n  - " + "\n  - ".join(runtime.blocking) if runtime.blocking else " (none captured)"
            logger.warning(
                f"[AnimV2] {frame_id} runtime FAIL attempt "
                f"{attempt}/{MAX_BROWSER_RETRY_ATTEMPTS}\n"
                f"---- RUNTIME BLOCKING ISSUES ----{full_blocking}\n"
                f"---- END RUNTIME ISSUES ----"
            )
            if progress_fn:
                progress_fn(f"[{frame_id}] runtime FAIL: {last_error[:80]}")
            continue

        # ── Narration + visual critic in parallel (after validation) ──
        # Narration receives validated GSAP labels so it's tuned to the
        # actual generated animation, not just storyboard descriptions.
        if progress_fn:
            progress_fn(f"[{frame_id}] generating narration + visual critique...")
        animation_context = {
            "validated_labels": runtime.labels_in_timeline,
        }
        narration_task = asyncio.create_task(
            generate_frame_narration(gemini, frame, animation_context=animation_context)
        )

        critic_task = None
        if runtime.screenshots_b64:
            async def _run_critic():
                vspec = frame.get("visual_spec", {})
                description = (vspec.get("description") or "")[:400]
                return await review_animation_screenshots(
                    screenshots_b64=runtime.screenshots_b64,
                    step_labels=runtime.step_labels_for_screenshots,
                    visual_type=frame.get("visual_type", "animation"),
                    description=description,
                )
            critic_task = asyncio.create_task(_run_critic())

        try:
            narrations = await asyncio.wait_for(narration_task, timeout=90.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
            logger.warning(f"[AnimV2] {frame_id} narration gen failed: {e}")
            narrations = None
        if narrations:
            result["narration_texts"] = narrations
            logger.info(
                f"[AnimV2] {frame_id} narration OK: {len(narrations)} steps, "
                f"avg {sum(len(t) for t in narrations) // len(narrations)} chars"
            )

        # ── Visual critic (advisory) ──
        if critic_task:
            try:
                visual = await asyncio.wait_for(critic_task, timeout=30.0)
                result["visual_critic"] = {
                    "score": visual.score,
                    "verdict": visual.verdict,
                    "issues": visual.issues,
                    "feedback": visual.feedback,
                }
                if not visual.passed:
                    logger.info(
                        f"[AnimV2] {frame_id} visual critic advisory: "
                        f"score={visual.score} verdict={visual.verdict}"
                    )
            except Exception as e:
                logger.warning(f"[AnimV2] {frame_id} visual critic crashed: {e}")

        if progress_fn:
            progress_fn(f"[{frame_id}] runtime PASS on attempt {attempt}")
        return result

    # All attempts failed — return the last result with a failure marker so
    # the lesson can still play with a placeholder frame.
    last_result["status"] = "failed"
    last_result.setdefault("error", last_error or "runtime validation failed")
    return last_result
