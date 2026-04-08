"""TEST 8: Edge cases — math notation, failed iframe display, broken animations.

Verifies:
1. Piper handles math notation as well as Kokoro
2. What the user sees when an animation HTML has a JS error
3. What happens for animations with only 1 step (like f14)
"""

import asyncio
import os
import sys
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from piper import PiperVoice, SynthesisConfig
from playwright.async_api import async_playwright

PIPER_DIR = os.path.join(os.path.dirname(__file__), "piper_voices")
ANIM_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "generated_visuals")
OUT_DIR = os.path.join(os.path.dirname(__file__), "edge_cases")
os.makedirs(OUT_DIR, exist_ok=True)


# Math-heavy text that the LLM might generate
MATH_TEXT = (
    "The probability density is one over square root of two pi sigma squared, "
    "times exp of negative x minus mu squared over two sigma squared. "
    "When sigma equals one and mu equals zero, this is the standard Gaussian. "
    "The expectation E of X is the integral of x times p of x dx. "
    "And the KL divergence is the sum over i of p of i times log p of i over q of i."
)


def test_math_handling():
    print("\n--- Test 8a: Piper math text handling ---")
    voice = PiperVoice.load(os.path.join(PIPER_DIR, "en_US-libritts_r-medium.onnx"))
    cfg = SynthesisConfig()

    audio_bytes = b""
    sr = 22050
    for chunk in voice.synthesize(MATH_TEXT, syn_config=cfg):
        audio_bytes += chunk.audio_int16_bytes
        sr = chunk.sample_rate

    out = os.path.join(OUT_DIR, "math_speech.wav")
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_bytes)

    duration = len(audio_bytes) / 2 / sr
    print(f"  Math text: {len(MATH_TEXT)} chars -> {duration:.1f}s audio")
    print(f"  Saved: {out}")
    print(f"  ==> Listen to verify pronunciation of 'sigma squared', 'KL divergence', etc.")


async def test_broken_animation_display():
    print("\n--- Test 8b: What user sees when animation fails ---")

    # Test with f14 which has a known .node() bug (still unfixed)
    f14_path = os.path.join(ANIM_DIR, "f14.html")
    file_url = "file:///" + os.path.abspath(f14_path).replace("\\", "/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        await page.goto(file_url)
        await asyncio.sleep(2)

        # Check what's in the canvas-container
        children_html = await page.evaluate("""
            () => {
                const c = document.getElementById('canvas-container');
                return {
                    childCount: c.children.length,
                    innerText: c.innerText || '(empty)',
                    innerHTML: c.innerHTML.substring(0, 200),
                };
            }
        """)
        print(f"  f14 canvas state:")
        print(f"    Child count: {children_html['childCount']}")
        print(f"    Inner text: '{children_html['innerText']}'")
        print(f"  Page errors: {errors}")

        # Take screenshot to see what's visible
        screenshot_path = os.path.join(OUT_DIR, "f14_broken_visual.png")
        await page.screenshot(path=screenshot_path)
        print(f"  Screenshot: {screenshot_path}")

        # Get steps
        steps = await page.evaluate("window.animationAPI ? window.animationAPI.getSteps() : null")
        print(f"  Available steps: {steps}")

        await browser.close()


async def test_iframe_with_overlay():
    """Demonstrate what a fallback overlay would look like."""
    print("\n--- Test 8c: Frame loader with title overlay (proposed solution) ---")

    # Build a wrapper HTML that:
    # - Has a title overlay (always visible)
    # - Embeds the animation iframe
    # - Has an error fallback when iframe fails
    wrapper_html = """
<!DOCTYPE html><html><head>
<style>
body { margin: 0; background: #0d1117; color: #c9d1d9; font-family: sans-serif; }
.classroom { position: relative; width: 100vw; height: 100vh; }
.title-overlay {
    position: absolute; top: 24px; left: 24px;
    background: rgba(13,17,23,0.8);
    padding: 12px 20px; border-radius: 8px;
    font-size: 14px; font-weight: bold;
    border: 1px solid rgba(255,255,255,0.1);
    z-index: 10;
}
.title-overlay .lesson-title { color: #8b949e; font-size: 11px; text-transform: uppercase; }
.title-overlay .frame-title { color: #f0f6fc; font-size: 18px; margin-top: 4px; }
.iframe-container { width: 100%; height: 100%; }
.iframe-container iframe { width: 100%; height: 100%; border: 0; }
.error-fallback {
    position: absolute; inset: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: #0d1117;
    text-align: center; padding: 40px;
}
.error-fallback h2 { color: #f0f6fc; margin: 0 0 12px; }
.error-fallback p { color: #8b949e; max-width: 500px; }
.error-fallback .icon { font-size: 64px; margin-bottom: 16px; opacity: 0.4; }
</style>
</head><body>
<div class="classroom">
    <div class="title-overlay">
        <div class="lesson-title">Diffusion Models — Lesson 1</div>
        <div class="frame-title">Frame 14: Variational Inference Intro</div>
    </div>
    <div class="iframe-container">
        <div class="error-fallback">
            <div class="icon">📊</div>
            <h2>Variational Inference Intro</h2>
            <p>Your AI teacher is explaining this concept. The visual for this frame couldn't load — listen to the narration.</p>
        </div>
    </div>
</div>
</body></html>
"""

    out_path = os.path.join(OUT_DIR, "fallback_demo.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(wrapper_html)

    file_url = "file:///" + os.path.abspath(out_path).replace("\\", "/")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(file_url)
        await asyncio.sleep(0.5)
        screenshot_path = os.path.join(OUT_DIR, "fallback_demo.png")
        await page.screenshot(path=screenshot_path)
        await browser.close()
    print(f"  Demo screenshot: {screenshot_path}")
    print(f"  Demo HTML: {out_path}")


def main():
    print("=" * 70)
    print("TEST 8: Edge cases")
    print("=" * 70)

    test_math_handling()
    asyncio.run(test_broken_animation_display())
    asyncio.run(test_iframe_with_overlay())

    print("\n" + "=" * 70)
    print(f"Outputs saved to: {OUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
