"""TEST 1: Measure Kokoro TTS baseline performance.

Goals:
- How long does cold start take?
- How long does warm synthesis take for various text lengths?
- Can we parallelize sentences for streaming?
- What's the realtime factor?
"""

import asyncio
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from kokoro_onnx import Kokoro

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

# Sample texts of varying length
SHORT = "Hi there, welcome to the lesson."  # ~10 words
MEDIUM = (
    "Look at this animation. The pixels are organizing themselves into "
    "structured patterns, slowly revealing a clear image of a face."
)  # ~25 words
LONG = (
    "Welcome back to the lesson on diffusion models. Today we will explore "
    "how random noise transforms into structured images through a learned "
    "denoising process. This is the same principle behind tools like Stable "
    "Diffusion and DALL-E. Let's start by looking at what happens when we "
    "add noise to an image, and then how a model learns to reverse that process."
)  # ~70 words


def measure_synth(kokoro, text: str, label: str) -> dict:
    """Synthesize text and measure time."""
    start = time.time()
    samples, sr = kokoro.create(text, voice="af_bella", speed=1.0)
    elapsed = time.time() - start
    audio_duration = len(samples) / sr
    rtf = audio_duration / elapsed  # realtime factor (>1 = faster than realtime)
    return {
        "label": label,
        "chars": len(text),
        "synth_time": elapsed,
        "audio_duration": audio_duration,
        "rtf": rtf,
    }


def main():
    print("=" * 70)
    print("TEST 1: Kokoro TTS baseline")
    print("=" * 70)

    # 1. Cold start
    print("\n1. Cold start (model load)...")
    t0 = time.time()
    kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
    cold_load = time.time() - t0
    print(f"   Model load: {cold_load:.2f}s")

    # 2. First synthesis (often slower than warm)
    print("\n2. First synthesis (likely warm-up cost)...")
    first = measure_synth(kokoro, SHORT, "first_short")
    print(f"   {first['label']}: {first['chars']}ch -> {first['audio_duration']:.1f}s audio in {first['synth_time']:.2f}s ({first['rtf']:.2f}x realtime)")

    # 3. Warm synthesis at various lengths
    print("\n3. Warm synthesis at various text lengths...")
    results = []
    for label, text in [("short", SHORT), ("medium", MEDIUM), ("long", LONG)]:
        # Run twice and take the second (truly warm) measurement
        measure_synth(kokoro, text, label)
        r = measure_synth(kokoro, text, label)
        results.append(r)
        print(f"   {r['label']}: {r['chars']}ch -> {r['audio_duration']:.1f}s audio in {r['synth_time']:.2f}s ({r['rtf']:.2f}x realtime)")

    # 4. Parallel synthesis test (simulate sentence streaming)
    print("\n4. Parallel synthesis (5 sentences concurrently via threads)...")
    sentences = [
        "The first sentence introduces the topic.",
        "The second sentence builds on the first.",
        "The third sentence adds detail.",
        "The fourth sentence emphasizes a key point.",
        "The fifth sentence concludes the section.",
    ]
    executor = ThreadPoolExecutor(max_workers=5)

    def synth_one(s):
        t0 = time.time()
        samples, sr = kokoro.create(s, voice="af_bella")
        return time.time() - t0, len(samples) / sr

    t0 = time.time()
    futures = [executor.submit(synth_one, s) for s in sentences]
    times = [f.result() for f in futures]
    parallel_total = time.time() - t0
    serial_total = sum(t for t, _ in times)
    audio_total = sum(d for _, d in times)
    print(f"   Sentences: {len(sentences)}")
    print(f"   Total audio: {audio_total:.1f}s")
    print(f"   Serial sum: {serial_total:.2f}s")
    print(f"   Parallel wall time: {parallel_total:.2f}s")
    print(f"   Speedup: {serial_total / parallel_total:.1f}x")

    # 5. First sentence latency (most important for streaming)
    print("\n5. First-sentence latency (lowest perceived wait)...")
    first_sentence = "Welcome to the lesson."
    times_first = []
    for _ in range(3):
        t0 = time.time()
        kokoro.create(first_sentence, voice="af_bella")
        times_first.append(time.time() - t0)
    print(f"   Tries: {[f'{t:.2f}s' for t in times_first]}")
    print(f"   Best: {min(times_first):.2f}s (this is the floor for first audio)")

    # 6. Long opening simulation (matches the 38s issue)
    print("\n6. Simulate the 38s opening problem...")
    long_opening = " ".join([
        "Hey there Aswin, welcome to our lesson on diffusion models.",
        "I'm so excited to dive into this with you.",
        "Today we are going to explore how noise transforms into structured images.",
        "This is the same technology behind tools like Stable Diffusion and DALL-E.",
        "We will start by looking at the forward diffusion process.",
        "Then we will see how a neural network learns to reverse it.",
        "By the end of this lesson, you'll understand the core mathematical idea.",
        "Are you ready? Let's get started!",
    ])
    t0 = time.time()
    samples, sr = kokoro.create(long_opening, voice="af_bella")
    full_synth = time.time() - t0
    full_audio = len(samples) / sr
    print(f"   Full opening: {len(long_opening)} chars")
    print(f"   Audio duration: {full_audio:.1f}s")
    print(f"   Synth time: {full_synth:.2f}s")
    print(f"   ==> User waits: {full_synth:.1f}s before hearing ANYTHING")

    # Now the streaming version
    print("\n7. Same opening, sentence-by-sentence...")
    parts = [
        "Hey there Aswin, welcome to our lesson on diffusion models.",
        "I'm so excited to dive into this with you.",
        "Today we are going to explore how noise transforms into structured images.",
        "This is the same technology behind tools like Stable Diffusion and DALL-E.",
        "We will start by looking at the forward diffusion process.",
        "Then we will see how a neural network learns to reverse it.",
        "By the end of this lesson, you'll understand the core mathematical idea.",
        "Are you ready? Let's get started!",
    ]

    t_start = time.time()
    futures = [executor.submit(synth_one, p) for p in parts]
    first_result_time = None
    completed_audio = 0
    for i, f in enumerate(futures):
        synth_t, audio_d = f.result()
        completed_audio += audio_d
        if i == 0:
            first_result_time = time.time() - t_start
    parallel_wall = time.time() - t_start
    print(f"   Sentences: {len(parts)}")
    print(f"   Total audio: {completed_audio:.1f}s")
    print(f"   First sentence ready: {first_result_time:.2f}s ← THIS is what user waits")
    print(f"   All sentences ready: {parallel_wall:.2f}s")
    print(f"   ==> User starts hearing in {first_result_time:.1f}s instead of {full_synth:.1f}s")

    executor.shutdown()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
