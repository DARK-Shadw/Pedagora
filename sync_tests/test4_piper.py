"""TEST 4: Benchmark Piper TTS as a faster alternative to Kokoro.

Goals:
- Cold start time
- Per-text synthesis time vs Kokoro
- Test true streaming (chunk-by-chunk)
- Compare quality (subjective via saved WAV)
"""

import io
import os
import sys
import time
import urllib.request
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from piper import PiperVoice, SynthesisConfig

VOICE_DIR = os.path.join(os.path.dirname(__file__), "piper_voices")
os.makedirs(VOICE_DIR, exist_ok=True)

# Use lessac (US female) — high quality, similar to Kokoro's Bella
VOICE_NAME = "en_US-lessac-medium"
ONNX_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/{VOICE_NAME}.onnx"
JSON_URL = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/{VOICE_NAME}.onnx.json"

ONNX_PATH = os.path.join(VOICE_DIR, f"{VOICE_NAME}.onnx")
JSON_PATH = os.path.join(VOICE_DIR, f"{VOICE_NAME}.onnx.json")

SHORT = "Hi there, welcome to the lesson."
MEDIUM = (
    "Look at this animation. The pixels are organizing themselves into "
    "structured patterns, slowly revealing a clear image of a face."
)
LONG_OPENING = " ".join([
    "Hey there Aswin, welcome to our lesson on diffusion models.",
    "I'm so excited to dive into this with you.",
    "Today we are going to explore how noise transforms into structured images.",
    "This is the same technology behind tools like Stable Diffusion and DALL-E.",
    "We will start by looking at the forward diffusion process.",
    "Then we will see how a neural network learns to reverse it.",
    "By the end of this lesson, you'll understand the core mathematical idea.",
    "Are you ready? Let's get started!",
])


def download():
    if os.path.exists(ONNX_PATH) and os.path.exists(JSON_PATH):
        print(f"  Voice already downloaded")
        return
    print(f"  Downloading {VOICE_NAME}...")
    for url, path in [(ONNX_URL, ONNX_PATH), (JSON_URL, JSON_PATH)]:
        urllib.request.urlretrieve(url, path)
    print(f"  Done. Size: {os.path.getsize(ONNX_PATH) // 1024 // 1024}MB")


def main():
    print("=" * 70)
    print("TEST 4: Piper TTS benchmark")
    print("=" * 70)

    print("\n1. Voice download...")
    download()

    print("\n2. Cold start (load voice)...")
    t0 = time.time()
    voice = PiperVoice.load(ONNX_PATH)
    cold = time.time() - t0
    print(f"   Load time: {cold:.2f}s")

    cfg = SynthesisConfig()

    def synth_blocking(text):
        """Collect all chunks into one buffer (blocking)."""
        t0 = time.time()
        chunks = list(voice.synthesize(text, syn_config=cfg))
        # Stitch the audio
        audio_bytes = b"".join(c.audio_int16_bytes for c in chunks)
        elapsed = time.time() - t0
        sample_rate = chunks[0].sample_rate if chunks else 22050
        # Each sample is 2 bytes (int16)
        audio_duration = len(audio_bytes) / 2 / sample_rate
        return elapsed, audio_duration, audio_bytes, sample_rate

    def synth_streaming(text):
        """Get time-to-first-chunk + total time."""
        t0 = time.time()
        first_chunk_time = None
        total_audio_bytes = b""
        sample_rate = 22050
        for chunk in voice.synthesize(text, syn_config=cfg):
            if first_chunk_time is None:
                first_chunk_time = time.time() - t0
            total_audio_bytes += chunk.audio_int16_bytes
            sample_rate = chunk.sample_rate
        total_time = time.time() - t0
        audio_duration = len(total_audio_bytes) / 2 / sample_rate
        return first_chunk_time, total_time, audio_duration

    print("\n3. Warm synthesis at various lengths...")
    # warm up
    synth_blocking("hello")

    for label, text in [("short", SHORT), ("medium", MEDIUM), ("long", LONG_OPENING)]:
        elapsed, audio_dur, audio_bytes, sr = synth_blocking(text)
        rtf = audio_dur / elapsed
        print(f"   {label:8s}: {len(text):4d}ch -> {audio_dur:5.1f}s audio in {elapsed:5.2f}s ({rtf:.2f}x realtime)")

        # Save sample for listening test
        out_path = os.path.join(VOICE_DIR, f"sample_{label}.wav")
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sr)
            wf.writeframes(audio_bytes)

    print("\n4. STREAMING test — time to first chunk...")
    print("   (This is the most important metric for low latency)")
    for label, text in [("short", SHORT), ("medium", MEDIUM), ("long", LONG_OPENING)]:
        # Run twice and take the second (warm) one
        synth_streaming(text)
        first, total, audio_dur = synth_streaming(text)
        print(f"   {label:8s}: first_chunk={first*1000:6.0f}ms  total={total:5.2f}s  audio={audio_dur:.1f}s")

    print("\n5. Reproduce the 38s opening problem with Piper...")
    elapsed, audio_dur, _, _ = synth_blocking(LONG_OPENING)
    print(f"   Full opening: {len(LONG_OPENING)} chars")
    print(f"   Audio duration: {audio_dur:.1f}s")
    print(f"   Synth time: {elapsed:.2f}s")
    print(f"   ==> User waits: {elapsed:.1f}s before hearing ANYTHING")

    first, total, audio_dur = synth_streaming(LONG_OPENING)
    print(f"\n   With streaming:")
    print(f"   First chunk: {first*1000:.0f}ms ← user starts hearing audio")
    print(f"   Total synth: {total:.2f}s")

    print("\n6. Comparison vs Kokoro:")
    print("   Metric              Kokoro       Piper")
    print(f"   Cold start          1.68s        {cold:.2f}s")
    print(f"   Long opening (full) 23.86s       {elapsed:.2f}s")
    print(f"   First audio (long)  ~7s (parallel) {first*1000:.0f}ms (streaming)")

    print(f"\nSamples saved to {VOICE_DIR}/sample_*.wav")
    print("Listen to short/medium/long to compare quality with Kokoro")


if __name__ == "__main__":
    main()
