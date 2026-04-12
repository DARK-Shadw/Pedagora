"""Test: can Gemini 3.1 Flash Lite generate a HARD Manim animation one-shot?

Measures:
  - Generation time (Gemini API call)
  - Output size
  - Syntax/class validation
  - Render time (manim subprocess)
  - MP4 size

Usage:
  python scripts/test_gemini_manim.py
"""

import asyncio
import os
import re
import sys
import time
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
except ImportError:
    pass

# Make backend importable for the real renderer
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from google import genai
from google.genai import types
from app.agents.animation.renderer import render_manim_scene


MODEL_ID = "gemini-3.1-flash-lite-preview"

SYSTEM_PROMPT = """You are a Manim CE v0.20 expert. Generate a SINGLE self-contained Python file.

STRICT REQUIREMENTS:
1. Start with: `from manim import *` and `import numpy as np`
2. Define exactly one class: `class AnimationScene(Scene):` (NOT ThreeDScene unless the prompt requires 3D)
3. If you need 3D, use `class AnimationScene(ThreeDScene):`
4. All animation logic inside `def construct(self):`
5. Keep total runtime under 15 seconds (use `self.wait(1)` sparingly)
6. Use Tex/MathTex for all math formulas
7. Return ONLY the Python code in a ```python ... ``` block. No explanation before or after.
8. Do not use deprecated APIs (no `ShowCreation` — use `Create`; no `get_graph` — use `plot`).
9. Every object must be added with `self.add` or animated in via `self.play`.
10. Imports and the class definition must be at module level.

Your code will be rendered with `manim -ql` (480p15, low quality for speed).
"""

# A genuinely hard prompt — the kind that made the real pipeline time out on Sonnet.
HARD_PROMPT = """Create a Manim animation that visualizes Maximum Likelihood Estimation for a Gaussian.

Requirements:
1. Left panel: show 12 scattered data points on a number line (x-axis from -4 to 4).
   The data is sampled from N(1.2, 0.8). Label them as `x_1, x_2, ... x_n`.

2. Right panel: show a coordinate plane with x-axis [-4, 4] and y-axis [0, 0.6].
   Draw a Gaussian PDF curve. Start with a "wrong" guess (mu=0, sigma=2) — show it thin and red.

3. Animate mu sliding from 0 → 1.2, and sigma shrinking from 2 → 0.8, so the curve
   smoothly morphs into the "true" distribution. Make it green when it fits.

4. At the top, show the log-likelihood formula in LaTeX:
       L(mu, sigma) = sum_i log( (1/(sigma*sqrt(2*pi))) * exp(-(x_i-mu)^2 / (2*sigma^2)) )
   As the curve morphs, show a number below the formula (e.g. "L = -34.2") that
   increases (becomes less negative) as the fit improves. Use always_redraw or
   a ValueTracker.

5. At the end, draw vertical drop lines from each data point up to the curve,
   showing how each sample contributes to the likelihood.

Total runtime ~15 seconds. Clean, readable, 3Blue1Brown style.
"""


def extract_python(text: str) -> str | None:
    text = text.strip()
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if text.startswith(("from manim", "import ", "class ")):
        return text
    return None


def validate(code: str) -> str | None:
    import ast
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"
    if "class AnimationScene" not in code:
        return "Missing 'class AnimationScene'"
    return None


async def main():
    print(f"=== Gemini {MODEL_ID} + Manim hard-prompt test ===\n")
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set")
        return 1

    client = genai.Client(api_key=api_key)

    # ── 1. Generate ──
    print(f">> Generating with {MODEL_ID}...")
    gen_start = time.time()
    try:
        resp = client.models.generate_content(
            model=MODEL_ID,
            contents=HARD_PROMPT,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=8192,
            ),
        )
    except Exception as e:
        print(f"!! API call failed: {e}")
        return 1
    gen_elapsed = time.time() - gen_start

    raw = resp.text or ""
    print(f"   Generation time: {gen_elapsed:.1f}s")
    print(f"   Raw response:    {len(raw)} chars")

    usage = getattr(resp, "usage_metadata", None)
    if usage:
        print(f"   Tokens: in={usage.prompt_token_count} out={usage.candidates_token_count}")

    # ── 2. Extract + validate ──
    code = extract_python(raw)
    if not code:
        print("!! No Python code extracted")
        print("--- raw response head ---")
        print(raw[:1500])
        return 1
    print(f"   Extracted code:  {len(code)} chars")

    err = validate(code)
    if err:
        print(f"!! Validation failed: {err}")
        print("--- code head ---")
        print(code[:1500])
        return 1
    print("   Validation:      PASS")

    # Save code for inspection
    code_path = Path(__file__).parent / "gemini_manim_test_output.py"
    code_path.write_text(code, encoding="utf-8")
    print(f"   Saved code:      {code_path}")

    # ── 3. Render ──
    print("\n>> Rendering with Manim (-ql, 480p15)...")
    output_dir = Path(__file__).parent / "gemini_manim_test_render"
    output_dir.mkdir(exist_ok=True)

    render_start = time.time()
    mp4_path, render_err = await render_manim_scene(
        code=code,
        output_dir=str(output_dir),
        quality="l",
        timeout=300,
    )
    render_elapsed = time.time() - render_start
    print(f"   Render time:     {render_elapsed:.1f}s")

    if render_err:
        print(f"!! Render FAILED: {render_err[-800:]}")
        return 1

    if not mp4_path or not os.path.exists(mp4_path):
        print("!! No MP4 produced")
        return 1

    size_kb = os.path.getsize(mp4_path) // 1024
    print(f"   MP4:             {mp4_path} ({size_kb} KB)")

    total = gen_elapsed + render_elapsed
    print("\n=== RESULT: SUCCESS ===")
    print(f"  Gen:    {gen_elapsed:.1f}s")
    print(f"  Render: {render_elapsed:.1f}s")
    print(f"  Total:  {total:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
