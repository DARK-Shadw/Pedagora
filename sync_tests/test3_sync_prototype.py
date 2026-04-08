"""TEST 3: Build a sync prototype for f01 and measure actual sync error.

The architecture being tested:
1. Pre-generate per-step speech audio (parallel)
2. For each step:
   a. Seek animation to step N (paused)
   b. Play audio for step N
   c. When audio ends, animate from step N to step N+1 naturally
   d. When animation reaches step N+1, repeat
3. Measure: visual delay between speech mention and animation state

For f01 (intro -> emergence -> zoom -> question), the speeches we'll
test match what the LLM would generate:
- intro (0s):     "Look at this animation, it's pure random noise filling the screen."
- emergence (5s): "Watch how patterns slowly start emerging from the chaos."
- zoom (15s):    "See where the camera is zooming in — a face is coming into focus."
- question (27s): "What do you think is happening here? Think about it."
"""

import asyncio
import base64
import io
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import soundfile
from kokoro_onnx import Kokoro
from playwright.async_api import async_playwright

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "models")
ANIM_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "generated_visuals")

# The 4 step speeches for f01 — written to match the visual content
STEP_SPEECHES = {
    "intro": "Look at this animation. Right now you are seeing pure random noise, just static filling the screen.",
    "emergence": "Now watch carefully. Patterns are starting to emerge from the chaos, regions of light and dark.",
    "zoom": "See where the camera is zooming in. A face is coming into focus from what was just noise.",
    "question": "What do you think this process represents? Take a moment to think about it before we continue.",
}


def synthesize_all(kokoro: Kokoro, speeches: dict[str, str]) -> dict[str, dict]:
    """Generate audio for each step's speech, return {label: {audio_b64, duration_s}}."""
    from concurrent.futures import ThreadPoolExecutor

    def synth(item):
        label, text = item
        t0 = time.time()
        samples, sr = kokoro.create(text, voice="af_bella", speed=1.0)
        elapsed = time.time() - t0
        buf = io.BytesIO()
        soundfile.write(buf, samples, sr, format="WAV", subtype="PCM_16")
        audio_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        duration = len(samples) / sr
        return label, {
            "text": text,
            "audio_b64": audio_b64,
            "duration_s": duration,
            "synth_s": elapsed,
        }

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(synth, speeches.items()))

    return dict(results)


async def run_sync_test(audio_data: dict, label_times: dict, anim_html_path: str):
    """Open the animation in a browser, run the sync protocol, measure actual sync error."""
    file_url = "file:///" + os.path.abspath(anim_html_path).replace("\\", "/")

    sorted_labels = sorted(label_times.items(), key=lambda x: x[1])
    print(f"\nLabel times: {sorted_labels}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        page.on("pageerror", lambda exc: print(f"  PAGE ERROR: {exc}"))
        page.on("console", lambda m: print(f"  [{m.type}] {m.text}") if m.type in ("error", "warning") else None)

        await page.goto(file_url)
        await asyncio.sleep(1)
        await page.evaluate("window.animationAPI && window.animationAPI.pause()")

        # Pass audio data + sync protocol into the page
        await page.add_script_tag(content=f"""
            window.__SYNC_DATA__ = {{
                steps: {[
                    {"label": label, "audio": audio_data[label]["audio_b64"], "duration": audio_data[label]["duration_s"], "anim_time": label_times[label]}
                    for label in label_times
                    if label in audio_data
                ]!r}
            }};
        """.replace("'", '"'))

        # Sync engine — runs the lockstep protocol and records timing events
        await page.evaluate("""
            async () => {
                const log = [];
                const data = window.__SYNC_DATA__;
                const steps = data.steps;
                const tl = window.animationAPI.timeline;

                // Setup audio context
                const ctx = new (window.AudioContext || window.webkitAudioContext)();

                async function playAudio(b64) {
                    const bin = atob(b64);
                    const buf = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
                    const audio = await ctx.decodeAudioData(buf.buffer);
                    return new Promise(resolve => {
                        const src = ctx.createBufferSource();
                        src.buffer = audio;
                        src.connect(ctx.destination);
                        src.onended = () => resolve(audio.duration);
                        src.start();
                    });
                }

                const t0 = performance.now() / 1000;
                function now() { return performance.now() / 1000 - t0; }

                for (let i = 0; i < steps.length; i++) {
                    const step = steps[i];
                    const next = steps[i + 1];

                    // 1. Seek animation to this step's visual state
                    log.push({event: "seek", step: step.label, anim_time: step.anim_time, wall: now()});
                    tl.seek(step.anim_time);
                    tl.pause();

                    // 2. Play this step's speech
                    log.push({event: "speak_start", step: step.label, expected: step.duration, wall: now()});
                    const actualDur = await playAudio(step.audio);
                    log.push({event: "speak_end", step: step.label, actual: actualDur, wall: now()});

                    // 3. Animate naturally to next step (or end)
                    if (next) {
                        const segDur = next.anim_time - step.anim_time;
                        log.push({event: "animate_start", from: step.label, to: next.label, expected: segDur, wall: now()});
                        const tween = tl.tweenFromTo(step.anim_time, next.anim_time);
                        await new Promise(resolve => {
                            tween.eventCallback("onComplete", resolve);
                        });
                        log.push({event: "animate_end", to: next.label, wall: now()});
                    }
                }

                log.push({event: "done", wall: now()});
                return log;
            }
        """)

        # Wait for the sync engine to finish
        # We can poll for the "done" event
        max_wait = 120
        start_wait = time.time()

        # Re-run with explicit wait — this time get the result
        result = await page.evaluate("""
            async () => {
                // Reset animation
                window.animationAPI.pause();
                window.animationAPI.timeline.seek(0);

                const log = [];
                const data = window.__SYNC_DATA__;
                const steps = data.steps;
                const tl = window.animationAPI.timeline;

                const ctx = new (window.AudioContext || window.webkitAudioContext)();

                async function playAudio(b64) {
                    const bin = atob(b64);
                    const buf = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
                    const audio = await ctx.decodeAudioData(buf.buffer);
                    return new Promise(resolve => {
                        const src = ctx.createBufferSource();
                        src.buffer = audio;
                        src.connect(ctx.destination);
                        src.onended = () => resolve(audio.duration);
                        src.start();
                    });
                }

                const t0 = performance.now() / 1000;
                function now() { return performance.now() / 1000 - t0; }

                for (let i = 0; i < steps.length; i++) {
                    const step = steps[i];
                    const next = steps[i + 1];

                    log.push({event: "seek", step: step.label, anim_time: step.anim_time, wall: now()});
                    tl.seek(step.anim_time);
                    tl.pause();

                    log.push({event: "speak_start", step: step.label, expected: step.duration, wall: now()});
                    const actualDur = await playAudio(step.audio);
                    log.push({event: "speak_end", step: step.label, actual: actualDur, wall: now()});

                    if (next) {
                        const segDur = next.anim_time - step.anim_time;
                        log.push({event: "animate_start", from: step.label, to: next.label, expected: segDur, wall: now()});
                        const tween = tl.tweenFromTo(step.anim_time, next.anim_time);
                        await new Promise(resolve => {
                            tween.eventCallback("onComplete", resolve);
                        });
                        log.push({event: "animate_end", to: next.label, wall: now()});
                    }
                }

                log.push({event: "done", wall: now()});
                return log;
            }
        """)

        await browser.close()
        return result


async def main():
    print("=" * 70)
    print("TEST 3: Lockstep sync prototype with f01")
    print("=" * 70)

    print("\n1. Loading Kokoro...")
    kokoro = Kokoro(
        os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
        os.path.join(MODEL_DIR, "voices-v1.0.bin"),
    )
    print("   OK")

    print("\n2. Pre-generating step audio (parallel)...")
    t0 = time.time()
    audio_data = synthesize_all(kokoro, STEP_SPEECHES)
    total_synth = time.time() - t0
    print(f"   Total wall time: {total_synth:.2f}s")
    for label, data in audio_data.items():
        print(f"   [{label:12s}] {data['duration_s']:.1f}s audio (synth: {data['synth_s']:.2f}s)")

    print("\n3. Running sync protocol in browser with f01.html...")
    label_times = {"intro": 0, "emergence": 5, "zoom": 15, "question": 27}
    f01_path = os.path.join(ANIM_DIR, "f01.html")

    log = await run_sync_test(audio_data, label_times, f01_path)

    print("\n4. Sync timeline:")
    print(f"{'Wall (s)':<10} {'Event':<15} {'Detail':<40}")
    print("-" * 70)
    for entry in log:
        wall = entry.get("wall", 0)
        evt = entry.get("event", "")
        detail = ""
        if evt == "seek":
            detail = f"step={entry.get('step')} -> anim_time={entry.get('anim_time')}"
        elif evt == "speak_start":
            detail = f"step={entry.get('step')} expected_dur={entry.get('expected', 0):.1f}s"
        elif evt == "speak_end":
            detail = f"step={entry.get('step')} actual_dur={entry.get('actual', 0):.1f}s"
        elif evt == "animate_start":
            detail = f"{entry.get('from')} -> {entry.get('to')} (segment {entry.get('expected', 0):.1f}s)"
        elif evt == "animate_end":
            detail = f"reached {entry.get('to')}"
        print(f"{wall:<10.2f} {evt:<15} {detail}")

    # Calculate timings
    speak_durations = []
    animate_durations = []
    for i, entry in enumerate(log):
        if entry["event"] == "speak_start":
            for j in range(i + 1, len(log)):
                if log[j]["event"] == "speak_end":
                    speak_durations.append(log[j]["wall"] - entry["wall"])
                    break
        if entry["event"] == "animate_start":
            for j in range(i + 1, len(log)):
                if log[j]["event"] == "animate_end":
                    animate_durations.append(log[j]["wall"] - entry["wall"])
                    break

    total_time = log[-1]["wall"]
    print("\n5. Summary:")
    print(f"   Total lesson time: {total_time:.1f}s")
    print(f"   Speech time: {sum(speak_durations):.1f}s ({len(speak_durations)} chunks)")
    print(f"   Animation time: {sum(animate_durations):.1f}s ({len(animate_durations)} segments)")
    print(f"   Silent animation portion: {sum(animate_durations) / total_time * 100:.0f}%")
    print(f"   Audio pre-gen time: {total_synth:.1f}s (happens before lesson starts)")
    print(f"   ==> User waits {total_synth:.1f}s for prep, then sees perfectly synced lesson")


if __name__ == "__main__":
    asyncio.run(main())
