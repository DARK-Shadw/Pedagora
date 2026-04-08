"""TEST 7: Side-by-side quality comparison.

Generates the SAME text using:
1. Kokoro (current) — af_bella voice
2. Piper Lessac Medium
3. Piper Lessac High
4. Piper LibriTTS-R Medium
5. Piper Amy Medium

Saves all to one folder so user can listen and pick favorite.
"""

import io
import os
import sys
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import soundfile
from kokoro_onnx import Kokoro
from piper import PiperVoice, SynthesisConfig

OUT_DIR = os.path.join(os.path.dirname(__file__), "voice_comparison")
os.makedirs(OUT_DIR, exist_ok=True)

KOKORO_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "models")
PIPER_DIR = os.path.join(os.path.dirname(__file__), "piper_voices")

# Sample text — natural teaching speech
SAMPLE_TEXT = (
    "Welcome back to our lesson on diffusion models. "
    "Today we are going to explore how random noise transforms into structured images. "
    "Look at this animation. The pixels on screen are organizing themselves "
    "into patterns. See where the camera is zooming in — a face is coming into focus. "
    "Pretty amazing, right?"
)


def save_kokoro(text):
    print("\n[Kokoro] af_bella")
    kokoro = Kokoro(
        os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx"),
        os.path.join(KOKORO_DIR, "voices-v1.0.bin"),
    )
    samples, sr = kokoro.create(text, voice="af_bella", speed=1.0)
    out = os.path.join(OUT_DIR, "1_kokoro_af_bella.wav")
    soundfile.write(out, samples, sr, format="WAV", subtype="PCM_16")
    duration = len(samples) / sr
    print(f"  Saved: {out}")
    print(f"  Duration: {duration:.1f}s, Sample rate: {sr}")


def save_piper(label, fname, text):
    print(f"\n[Piper] {label}")
    onnx_path = os.path.join(PIPER_DIR, f"{fname}.onnx")
    if not os.path.exists(onnx_path):
        print(f"  SKIP - voice not downloaded: {onnx_path}")
        return
    voice = PiperVoice.load(onnx_path)
    cfg = SynthesisConfig()

    audio_bytes = b""
    sr = 22050
    for chunk in voice.synthesize(text, syn_config=cfg):
        audio_bytes += chunk.audio_int16_bytes
        sr = chunk.sample_rate

    out = os.path.join(OUT_DIR, f"{label}.wav")
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_bytes)
    duration = len(audio_bytes) / 2 / sr
    print(f"  Saved: {out}")
    print(f"  Duration: {duration:.1f}s, Sample rate: {sr}")


def main():
    print("=" * 70)
    print("TEST 7: Side-by-side voice quality comparison")
    print("=" * 70)
    print(f"\nSample text ({len(SAMPLE_TEXT)} chars):")
    print(f'  "{SAMPLE_TEXT[:80]}..."')

    save_kokoro(SAMPLE_TEXT)
    save_piper("2_piper_lessac_medium", "en_US-lessac-medium", SAMPLE_TEXT)
    save_piper("3_piper_lessac_high", "en_US-lessac-high", SAMPLE_TEXT)
    save_piper("4_piper_libritts_medium", "en_US-libritts_r-medium", SAMPLE_TEXT)
    save_piper("5_piper_amy_medium", "en_US-amy-medium", SAMPLE_TEXT)

    print("\n" + "=" * 70)
    print(f"All samples saved to: {OUT_DIR}")
    print("Listen to each in order and pick your favorite.")
    print("Recommended file manager: open the folder + double-click to play")
    print("=" * 70)


if __name__ == "__main__":
    main()
