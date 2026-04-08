"""Piper TTS — fast neural TTS via ONNX with streaming support.

Replaces Kokoro. Benchmarks (sync_tests/test4_piper.py):
- Cold start: ~3s (one-time)
- Long opening (478ch): 1.96s synth, 241ms first chunk
- Realtime factor: 13.21x (vs Kokoro's 1.16x)

Voice: en_US-libritts_r-medium (chosen by user from A/B test)
"""

import asyncio
import base64
import io
import logging
import time
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

VOICE_NAME = "en_US-libritts_r-medium"
VOICE_URL_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium"
)
MODEL_DIR = Path(__file__).parent.parent.parent / "models"

# Speech speed control: Piper's length_scale > 1.0 = slower, < 1.0 = faster.
# Default 1.0 sounds rushed and robotic for teaching content. 1.25 = ~25% slower,
# closer to a deliberate human teacher pace.
LENGTH_SCALE = 1.25

_voice = None
# Piper is CPU-bound; serial execution avoids GIL/core contention.
# Throughput stays high because Piper itself is ~13x realtime on a single thread.
_executor = ThreadPoolExecutor(max_workers=1)


@dataclass
class AudioResult:
    audio_b64: str       # base64-encoded WAV (with header)
    duration_s: float
    sample_rate: int


def _ensure_voice() -> Path:
    """Download voice model if missing. Returns path to ONNX file."""
    onnx_path = MODEL_DIR / f"{VOICE_NAME}.onnx"
    json_path = MODEL_DIR / f"{VOICE_NAME}.onnx.json"
    if onnx_path.exists() and json_path.exists():
        return onnx_path

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"[TTS] Downloading Piper voice {VOICE_NAME}...")
    for fname, dst in [
        (f"{VOICE_NAME}.onnx", onnx_path),
        (f"{VOICE_NAME}.onnx.json", json_path),
    ]:
        urllib.request.urlretrieve(f"{VOICE_URL_BASE}/{fname}", dst)
    logger.info(f"[TTS] Voice downloaded to {onnx_path}")
    return onnx_path


def _get_voice():
    """Lazy-load Piper voice. ~3s on first call."""
    global _voice
    if _voice is None:
        from piper import PiperVoice
        onnx_path = _ensure_voice()
        t0 = time.time()
        _voice = PiperVoice.load(str(onnx_path))
        logger.info(f"[TTS] Piper voice loaded in {time.time() - t0:.1f}s")
    return _voice


def _synthesize_sync(text: str) -> AudioResult:
    """Blocking synthesis. Runs inside the thread pool to keep the event loop free."""
    from piper import SynthesisConfig
    voice = _get_voice()
    cfg = SynthesisConfig(length_scale=LENGTH_SCALE)

    audio_bytes = b""
    sr = 22050
    for chunk in voice.synthesize(text, syn_config=cfg):
        audio_bytes += chunk.audio_int16_bytes
        sr = chunk.sample_rate

    # Wrap raw int16 PCM in a WAV container so the browser can decodeAudioData
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sr)
        wf.writeframes(audio_bytes)

    audio_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    duration = len(audio_bytes) / 2 / sr
    return AudioResult(audio_b64=audio_b64, duration_s=duration, sample_rate=sr)


async def warmup() -> None:
    """Pre-load Piper voice. Call from app startup or session create."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _get_voice)


async def text_to_audio_with_duration(text: str) -> AudioResult:
    """Convert text to base64 WAV + duration. Used by audio_cache."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _synthesize_sync, text)


async def text_to_audio_base64(
    text: str,
    voice: str = "",
    speed: float = 1.0,
) -> str:
    """Backwards-compatible interface used by the existing teacher router.

    `voice` and `speed` are accepted but ignored — Piper voice is fixed.
    """
    result = await text_to_audio_with_duration(text)
    return result.audio_b64
