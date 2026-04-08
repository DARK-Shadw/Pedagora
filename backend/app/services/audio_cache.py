"""Per-session audio cache with background prefetch.

Each teaching session has its own cache. Prefetch tasks run in the background
during session creation, masking the synthesis cost behind the user's
splash-screen wait. By the time playback reaches frame N, audio for frames
N+1..N+k is typically already cached (validated in sync_tests/test6_prefetch.py).

Memory: ~1MB per frame, ~20MB per 19-frame lesson. With 50 concurrent
sessions = 1GB max — acceptable for our scale.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from app.services.tts import text_to_audio_with_duration

logger = logging.getLogger(__name__)


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
        """Generate audio for one frame. Idempotent."""
        async with self._lock:
            if frame_id in self._frames:
                return self._frames[frame_id]
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
                audio = await text_to_audio_with_duration(text)
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
