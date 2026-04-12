"""Per-session audio cache with background prefetch + persistent disk layer.

Each teaching session has its own in-memory cache. Prefetch tasks run in the
background during session creation, masking the synthesis cost behind the
user's splash-screen wait. By the time playback reaches frame N, audio for
frames N+1..N+k is typically already cached (validated in test6_prefetch.py).

Below the in-memory cache sits `DiskAudioCache` — a content-addressed,
LRU-evicted on-disk store keyed by SHA256(voice|text). The first run pays
Piper synthesis cost; subsequent runs hit disk and return in <50 ms per step.
This is the difference between "regenerate the lesson takes minutes" and
"regenerate the lesson takes seconds" during iteration.

Memory: ~1MB per frame, ~20MB per 19-frame lesson. With 50 concurrent
sessions = 1GB max — acceptable for our scale.
Disk: 2 GB cap, mtime-based LRU eviction.
"""

import asyncio
import hashlib
import json as _json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.services.tts import AudioResult, text_to_audio_with_duration

logger = logging.getLogger(__name__)


# ── Persistent disk cache ───

# Bump this when the voice / synthesis config changes so old entries miss.
DISK_CACHE_VOICE_KEY = "piper-en_US-amy-medium-v1"
DISK_CACHE_DIR = Path(__file__).resolve().parents[3] / "audio_cache"
DISK_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


class DiskAudioCache:
    """Content-addressed disk cache for synthesized audio.

    Layout: `audio_cache/<sha256>.json` containing
    `{audio_b64, duration_s, sample_rate}`. Touched (utime) on every read so
    LRU eviction sees real usage. Eviction runs every N writes once the
    directory tops `max_bytes` — cheap, no DB, no index file.
    """

    _SCAN_EVERY = 25  # run eviction check every N writes

    def __init__(
        self,
        root: Path = DISK_CACHE_DIR,
        max_bytes: int = DISK_CACHE_MAX_BYTES,
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self._put_count = 0
        self._lock = asyncio.Lock()

    def _path_for(self, text: str) -> Path:
        key = f"{DISK_CACHE_VOICE_KEY}|{text}".encode("utf-8")
        h = hashlib.sha256(key).hexdigest()
        return self.root / f"{h}.json"

    async def get(self, text: str) -> AudioResult | None:
        path = self._path_for(text)
        if not path.exists():
            return None
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            os.utime(path, None)  # touch mtime so LRU keeps it warm
            return AudioResult(
                audio_b64=data["audio_b64"],
                duration_s=float(data["duration_s"]),
                sample_rate=int(data["sample_rate"]),
            )
        except Exception as e:
            logger.warning(f"[DiskAudioCache] read failed for {path.name}: {e}")
            return None

    async def put(self, text: str, result: AudioResult) -> None:
        path = self._path_for(text)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            path.write_text(
                _json.dumps({
                    "audio_b64": result.audio_b64,
                    "duration_s": result.duration_s,
                    "sample_rate": result.sample_rate,
                }),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[DiskAudioCache] write failed for {path.name}: {e}")
            return

        async with self._lock:
            self._put_count += 1
            if self._put_count % self._SCAN_EVERY == 0:
                # Eviction is filesystem-bound — push to a thread.
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._evict_if_over)

    def _evict_if_over(self) -> None:
        try:
            entries: list[tuple[float, int, Path]] = []
            total = 0
            for p in self.root.glob("*.json"):
                try:
                    st = p.stat()
                    entries.append((st.st_mtime, st.st_size, p))
                    total += st.st_size
                except OSError:
                    continue
            if total <= self.max_bytes:
                return
            entries.sort()  # oldest first
            target = int(self.max_bytes * 0.9)  # trim to 90% to avoid thrash
            removed = 0
            for _, size, p in entries:
                if total <= target:
                    break
                try:
                    p.unlink()
                    total -= size
                    removed += 1
                except OSError:
                    pass
            logger.info(
                f"[DiskAudioCache] evicted {removed} entries, "
                f"now {total / 1024 / 1024:.1f} MB"
            )
        except Exception as e:
            logger.warning(f"[DiskAudioCache] eviction failed: {e}")


# Module-level singleton — one disk cache process-wide.
_disk_cache = DiskAudioCache()


def get_disk_cache() -> DiskAudioCache:
    return _disk_cache


@dataclass
class StepAudio:
    """One animation step with its narration audio."""
    label: str
    anim_time: float
    text: str
    audio_b64: str   # base64 WAV; empty string means synthesis failed
    duration_s: float


@dataclass
class FrameAudio:
    """All step audio for one frame."""
    frame_id: str
    steps: list[StepAudio] = field(default_factory=list)
    error: str | None = None  # set if the whole frame failed


class SessionAudioCache:
    """Per-session audio cache with in-flight prefetch tracking.

    Idempotent: prefetch() returns the cached entry if already done, or awaits
    the in-flight task. get() blocks until ready (or returns None if cancelled).
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._frames: dict[str, FrameAudio] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._cancelled = False

    async def prefetch(
        self,
        frame_id: str,
        step_specs: list[dict],  # [{label, anim_time, text}, ...]
    ) -> FrameAudio:
        """Generate audio for one frame. Idempotent unless step count changed.

        If the cached entry has a different number of steps than step_specs,
        the cache is invalidated and re-generated. This handles the case where
        session-creation prefetch used a 1-step fallback but the real step
        extraction later found multiple steps.
        """
        async with self._lock:
            if frame_id in self._frames:
                cached = self._frames[frame_id]
                # Compare both step count AND text content — the prefetch
                # may have cached fallback text ("Now, the single die.")
                # while the teaching path has real Opus narration.
                new_texts = tuple(s.get("text", "") for s in step_specs)
                cached_texts = tuple(s.text for s in cached.steps)
                if new_texts == cached_texts:
                    return cached
                # Text changed — invalidate stale entry
                print(
                    f"[AudioCache] {frame_id} INVALIDATING stale cache: "
                    f"{len(cached.steps)} steps/{sum(len(t) for t in cached_texts)}ch "
                    f"-> {len(step_specs)} steps/{sum(len(t) for t in new_texts)}ch",
                    flush=True,
                )
                del self._frames[frame_id]
            if frame_id in self._tasks:
                task = self._tasks[frame_id]
            else:
                task = asyncio.create_task(self._do_prefetch(frame_id, step_specs))
                self._tasks[frame_id] = task

        try:
            return await task
        except asyncio.CancelledError:
            return FrameAudio(frame_id=frame_id, error="cancelled")

    async def _do_prefetch(
        self,
        frame_id: str,
        step_specs: list[dict],
    ) -> FrameAudio:
        if self._cancelled:
            return FrameAudio(frame_id=frame_id, error="cancelled")

        steps: list[StepAudio] = []
        for spec in step_specs:
            text = (spec.get("text") or "").strip()
            label = spec.get("label", "")
            anim_time = float(spec.get("anim_time", 0.0))

            if not text:
                # No speech for this step — keep an empty placeholder so the
                # frontend still seeks to the step (visual transition only).
                steps.append(StepAudio(
                    label=label,
                    anim_time=anim_time,
                    text="",
                    audio_b64="",
                    duration_s=0.0,
                ))
                continue

            try:
                # Disk cache fall-through: hits return in <50 ms.
                audio = await _disk_cache.get(text)
                if audio is None:
                    audio = await text_to_audio_with_duration(text)
                    await _disk_cache.put(text, audio)
                steps.append(StepAudio(
                    label=label,
                    anim_time=anim_time,
                    text=text,
                    audio_b64=audio.audio_b64,
                    duration_s=audio.duration_s,
                ))
            except Exception as e:
                logger.error(
                    f"[AudioCache] {frame_id} step {label} synth failed: {e}"
                )
                # Empty audio b64 — frontend shows subtitle without playback
                steps.append(StepAudio(
                    label=label,
                    anim_time=anim_time,
                    text=text,
                    audio_b64="",
                    duration_s=0.0,
                ))

        result = FrameAudio(frame_id=frame_id, steps=steps)
        async with self._lock:
            self._frames[frame_id] = result
            self._tasks.pop(frame_id, None)
        logger.info(
            f"[AudioCache] {self.session_id} cached {frame_id}: "
            f"{len(steps)} steps ({sum(s.duration_s for s in steps):.1f}s audio)"
        )
        return result

    async def get(self, frame_id: str) -> FrameAudio | None:
        """Get cached frame audio. Awaits in-progress prefetch.

        Returns None if the frame was never prefetched and no task is running.
        """
        async with self._lock:
            if frame_id in self._frames:
                return self._frames[frame_id]
            task = self._tasks.get(frame_id)
        if task:
            try:
                return await task
            except asyncio.CancelledError:
                return None
        return None

    def cancel(self) -> None:
        """Cancel all in-flight prefetches and clear cache. Safe to call multiple times."""
        self._cancelled = True
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._frames.clear()


# ── Global registry ───

_caches: dict[str, SessionAudioCache] = {}
_caches_lock = asyncio.Lock()


async def get_or_create_cache(session_id: str) -> SessionAudioCache:
    """Get or create the audio cache for a session."""
    async with _caches_lock:
        if session_id not in _caches:
            _caches[session_id] = SessionAudioCache(session_id)
        return _caches[session_id]


async def discard_cache(session_id: str) -> None:
    """Remove a session's cache and cancel pending tasks. Idempotent."""
    async with _caches_lock:
        cache = _caches.pop(session_id, None)
    if cache:
        cache.cancel()
        logger.info(f"[AudioCache] discarded {session_id}")
