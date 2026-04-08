"""TEST 5: Compare Piper voice quality options + run sync prototype with Piper.

Tests:
- lessac-medium (current)
- lessac-high (higher quality)
- libritts-high (multi-speaker, often considered best)
- Run f01 sync prototype with Piper, measure end-to-end timing
"""

import asyncio
import base64
import io
import os
import sys
import time
import urllib.request
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from piper import PiperVoice, SynthesisConfig
from playwright.async_api import async_playwright

VOICE_DIR = os.path.join(os.path.dirname(__file__), "piper_voices")
ANIM_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "generated_visuals")

# Voices to test — varying quality/speed tradeoffs
VOICES = [
    {
        "name": "en_US-lessac-medium",
        "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium",
        "label": "Lessac Medium (current default)",
    },
    {
        "name": "en_US-lessac-high",
        "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high",
        "label": "Lessac High (higher quality)",
    },
    {
        "name": "en_US-libritts_r-medium",
        "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium",
        "label": "LibriTTS-R Medium (multi-speaker)",
    },
    {
        "name": "en_US-amy-medium",
        "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium",
        "label": "Amy Medium (popular friendly voice)",
    },
]


def download_voice(v):
    onnx_path = os.path.join(VOICE_DIR, f"{v['name']}.onnx")
    json_path = os.path.join(VOICE_DIR, f"{v['name']}.onnx.json")
    if os.path.exists(onnx_path) and os.path.exists(json_path):
        return onnx_path, json_path
    print(f"  Downloading {v['name']}...")
    for fname, dst in [(f"{v['name']}.onnx", onnx_path), (f"{v['name']}.onnx.json", json_path)]:
        urllib.request.urlretrieve(f"{v['url_base']}/{fname}", dst)
    return onnx_path, json_path


SAMPLE_TEXT = (
    "Look at this animation. Right now you are seeing pure random noise, "
    "just static filling the screen. But watch carefully — patterns are "
    "starting to emerge from the chaos."
)


def benchmark_voice(v):
    print(f"\n--- {v['label']} ({v['name']}) ---")
    onnx_path, _ = download_voice(v)

    t0 = time.time()
    voice = PiperVoice.load(onnx_path)
    load = time.time() - t0
    print(f"  Load: {load:.2f}s, model size: {os.path.getsize(onnx_path) // 1024 // 1024}MB")

    cfg = SynthesisConfig()

    # Warm up
    list(voice.synthesize("hi", syn_config=cfg))

    # Streaming first-chunk
    t0 = time.time()
    first_chunk = None
    audio_bytes = b""
    sr = 22050
    for chunk in voice.synthesize(SAMPLE_TEXT, syn_config=cfg):
        if first_chunk is None:
            first_chunk = time.time() - t0
        audio_bytes += chunk.audio_int16_bytes
        sr = chunk.sample_rate
    total = time.time() - t0
    audio_dur = len(audio_bytes) / 2 / sr
    print(f"  First chunk: {first_chunk*1000:.0f}ms")
    print(f"  Total synth: {total:.2f}s")
    print(f"  Audio: {audio_dur:.1f}s ({audio_dur/total:.1f}x realtime)")
    print(f"  Sample rate: {sr} Hz")

    # Save sample
    out_path = os.path.join(VOICE_DIR, f"compare_{v['name']}.wav")
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_bytes)
    print(f"  Saved: compare_{v['name']}.wav")

    return voice, sr


async def run_sync_with_piper(voice, sample_rate):
    """Run f01 sync prototype using Piper instead of Kokoro."""
    print("\n" + "=" * 70)
    print("SYNC PROTOTYPE: f01 with Piper")
    print("=" * 70)

    STEP_SPEECHES = {
        "intro": "Look at this animation. Right now you are seeing pure random noise, just static filling the screen.",
        "emergence": "Now watch carefully. Patterns are starting to emerge from the chaos, regions of light and dark.",
        "zoom": "See where the camera is zooming in. A face is coming into focus from what was just noise.",
        "question": "What do you think this process represents? Take a moment to think about it before we continue.",
    }

    cfg = SynthesisConfig()

    print("\nGenerating audio for all 4 steps...")
    audio_data = {}
    t_total = time.time()
    for label, text in STEP_SPEECHES.items():
        t0 = time.time()
        audio_bytes = b""
        for chunk in voice.synthesize(text, syn_config=cfg):
            audio_bytes += chunk.audio_int16_bytes
        elapsed = time.time() - t0
        audio_dur = len(audio_bytes) / 2 / sample_rate

        # Wrap in WAV header
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)
        audio_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        audio_data[label] = {
            "audio_b64": audio_b64,
            "duration_s": audio_dur,
            "synth_s": elapsed,
        }
        print(f"  [{label:12s}] {audio_dur:.1f}s audio in {elapsed:.2f}s")

    pregen_total = time.time() - t_total
    print(f"\nTotal pre-gen time: {pregen_total:.2f}s (Kokoro was 30.5s — {30.5/pregen_total:.0f}x speedup)")

    # Now run sync test in browser
    label_times = {"intro": 0, "emergence": 5, "zoom": 15, "question": 27}
    f01_path = os.path.join(ANIM_DIR, "f01.html")
    file_url = "file:///" + os.path.abspath(f01_path).replace("\\", "/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        page.on("pageerror", lambda exc: print(f"  PAGE ERROR: {exc}"))

        await page.goto(file_url)
        await asyncio.sleep(1)

        steps_payload = [
            {"label": label, "audio": audio_data[label]["audio_b64"], "duration": audio_data[label]["duration_s"], "anim_time": label_times[label]}
            for label in label_times
        ]

        import json as _json
        steps_json = _json.dumps(steps_payload)

        result = await page.evaluate(f"""
            async () => {{
                window.animationAPI.pause();
                window.animationAPI.timeline.seek(0);

                const steps = {steps_json};
                const tl = window.animationAPI.timeline;
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const log = [];

                async function playAudio(b64) {{
                    const bin = atob(b64);
                    const buf = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
                    const audio = await ctx.decodeAudioData(buf.buffer);
                    return new Promise(resolve => {{
                        const src = ctx.createBufferSource();
                        src.buffer = audio;
                        src.connect(ctx.destination);
                        src.onended = () => resolve(audio.duration);
                        src.start();
                    }});
                }}

                const t0 = performance.now() / 1000;
                function now() {{ return performance.now() / 1000 - t0; }}

                for (let i = 0; i < steps.length; i++) {{
                    const step = steps[i];
                    const next = steps[i + 1];

                    log.push({{event: "seek", step: step.label, anim_time: step.anim_time, wall: now()}});
                    tl.seek(step.anim_time);
                    tl.pause();

                    log.push({{event: "speak_start", step: step.label, expected: step.duration, wall: now()}});
                    const actualDur = await playAudio(step.audio);
                    log.push({{event: "speak_end", step: step.label, actual: actualDur, wall: now()}});

                    if (next) {{
                        const segDur = next.anim_time - step.anim_time;
                        log.push({{event: "animate_start", from: step.label, to: next.label, expected: segDur, wall: now()}});
                        const tween = tl.tweenFromTo(step.anim_time, next.anim_time);
                        await new Promise(resolve => {{
                            tween.eventCallback("onComplete", resolve);
                        }});
                        log.push({{event: "animate_end", to: next.label, wall: now()}});
                    }}
                }}

                log.push({{event: "done", wall: now()}});
                return log;
            }}
        """)

        await browser.close()

    print("\nSync execution timeline:")
    for entry in result:
        wall = entry.get("wall", 0)
        evt = entry.get("event", "")
        detail = ""
        if evt == "seek":
            detail = f"step={entry.get('step')}"
        elif evt == "speak_start":
            detail = f"step={entry.get('step')} expected={entry.get('expected', 0):.1f}s"
        elif evt == "speak_end":
            detail = f"actual={entry.get('actual', 0):.1f}s"
        elif evt == "animate_start":
            detail = f"{entry.get('from')} -> {entry.get('to')} ({entry.get('expected', 0):.1f}s)"
        elif evt == "animate_end":
            detail = f"reached {entry.get('to')}"
        print(f"  {wall:6.2f}s  {evt:15s} {detail}")

    total_time = result[-1]["wall"]
    print(f"\nTotal lesson runtime: {total_time:.1f}s")
    print(f"Pre-gen + lesson: {pregen_total + total_time:.1f}s")
    print(f"User waits {pregen_total:.1f}s before lesson starts (vs 30.5s with Kokoro)")


def main():
    print("=" * 70)
    print("TEST 5: Piper voice quality + sync prototype")
    print("=" * 70)

    voice = None
    sr = 22050
    for v in VOICES:
        try:
            voice_obj, sr_obj = benchmark_voice(v)
            # Keep the highest-quality one available for the sync test
            if "lessac-high" in v["name"]:
                voice = voice_obj
                sr = sr_obj
            elif voice is None:
                voice = voice_obj
                sr = sr_obj
        except Exception as e:
            print(f"  FAILED: {e}")

    print(f"\n{'=' * 70}")
    print("Voice samples saved to:", VOICE_DIR)
    print("Files: compare_*.wav — listen to compare quality")
    print(f"{'=' * 70}")

    if voice is not None:
        asyncio.run(run_sync_with_piper(voice, sr))


if __name__ == "__main__":
    main()
