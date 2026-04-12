"""Shared helpers for the sync test harness.

Factored out of `test3_sync_prototype.py` so multiple CLI scripts can drive
the same end-to-end pipeline: extract step labels from a rendered animation,
synthesize per-step Piper audio, drive the lockstep protocol in Playwright,
measure drift, and write a JSON report.

Used by `scripts/sync_test.py` (full CLI) and `scripts/sync_test_single.py`
(CI smoke test). Keep this file dependency-light — only Playwright + the
backend's TTS service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Allow `python sync_tests/...` to import from `backend/`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.audio_cache import get_disk_cache  # noqa: E402
from app.services.tts import AudioResult, text_to_audio_with_duration  # noqa: E402

logger = logging.getLogger(__name__)


# ── GSAP label extraction ───

_LABEL_RE = re.compile(r"tl\.addLabel\(['\"]([^'\"]+)['\"]")


def extract_gsap_labels(html: str) -> list[str]:
    """Return GSAP `tl.addLabel('X', ...)` names in source order, deduped."""
    labels = _LABEL_RE.findall(html)
    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


# ── Audio synthesis (with disk cache) ───

@dataclass
class StepAudio:
    label: str
    text: str
    audio_b64: str
    duration_s: float
    synth_seconds: float = 0.0
    cache_hit: bool = False


async def synth_step(label: str, text: str) -> StepAudio:
    """Synthesize one step's audio. Hits disk cache if warm."""
    if not text.strip():
        return StepAudio(label=label, text="", audio_b64="", duration_s=0.0)

    disk = get_disk_cache()
    t0 = time.time()
    cached = await disk.get(text)
    if cached is not None:
        return StepAudio(
            label=label,
            text=text,
            audio_b64=cached.audio_b64,
            duration_s=cached.duration_s,
            synth_seconds=time.time() - t0,
            cache_hit=True,
        )
    audio: AudioResult = await text_to_audio_with_duration(text)
    await disk.put(text, audio)
    return StepAudio(
        label=label,
        text=text,
        audio_b64=audio.audio_b64,
        duration_s=audio.duration_s,
        synth_seconds=time.time() - t0,
    )


async def synth_steps(pairs: list[tuple[str, str]]) -> list[StepAudio]:
    """Synthesize a list of (label, text) pairs in parallel."""
    return await asyncio.gather(*(synth_step(l, t) for l, t in pairs))


# ── Playwright lockstep runner ───

LOCKSTEP_RUNNER_JS = r"""
async (data) => {
    const log = [];
    const errors = [];
    const steps = data.steps;

    const t0 = performance.now() / 1000;
    const now = () => performance.now() / 1000 - t0;

    if (!window.animationAPI || !window.animationAPI.timeline) {
        return { log: [], errors: ["window.animationAPI.timeline missing"], stepLabels: [] };
    }
    const tl = window.animationAPI.timeline;

    // Capture every label crossed via GSAP onUpdate
    const stepLabels = [];
    const labelsByTime = (tl.labels || {});
    const labelTimes = Object.keys(labelsByTime).map(name => ({
        name, time: labelsByTime[name]
    })).sort((a, b) => a.time - b.time);

    let lastReportedIdx = -1;
    tl.eventCallback("onUpdate", () => {
        const t = tl.time();
        for (let i = 0; i < labelTimes.length; i++) {
            if (t >= labelTimes[i].time && i > lastReportedIdx) {
                lastReportedIdx = i;
                stepLabels.push({ label: labelTimes[i].name, wall: now(), anim_time: t });
            }
        }
    });

    const ctx = new (window.AudioContext || window.webkitAudioContext)();

    async function playAudio(b64) {
        if (!b64) return 0;
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

    // Start paused
    try { tl.pause(); tl.seek(0); } catch (e) { errors.push("seek0 failed: " + e); }

    for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        const next = steps[i + 1];

        // 1. Seek to this step's label
        log.push({ event: "seek_start", step: step.label, wall: now() });
        try {
            const lt = labelsByTime[step.label];
            if (lt !== undefined) {
                tl.seek(lt);
            } else {
                errors.push("label not found in timeline: " + step.label);
            }
            tl.pause();
        } catch (e) {
            errors.push("seek failed " + step.label + ": " + e);
        }
        log.push({ event: "seek_end", step: step.label, anim_time: tl.time(), wall: now() });

        // 2. Play this step's narration
        log.push({ event: "speak_start", step: step.label, expected_dur: step.duration, wall: now() });
        try {
            const actual = await playAudio(step.audio);
            log.push({ event: "speak_end", step: step.label, actual_dur: actual, wall: now() });
        } catch (e) {
            errors.push("audio playback failed " + step.label + ": " + e);
            log.push({ event: "speak_end", step: step.label, actual_dur: 0, wall: now(), error: String(e) });
        }

        // 3. Animate to next step's label (or run to end)
        const nextLabel = next ? next.label : null;
        const nextTime = nextLabel ? labelsByTime[nextLabel] : tl.duration();
        if (nextTime !== undefined && nextTime > tl.time()) {
            log.push({ event: "animate_start", from: step.label, to: nextLabel, wall: now() });
            try {
                const tween = tl.tweenFromTo(tl.time(), nextTime);
                await new Promise(resolve => {
                    tween.eventCallback("onComplete", resolve);
                });
            } catch (e) {
                errors.push("tween failed " + step.label + "->" + nextLabel + ": " + e);
            }
            log.push({ event: "animate_end", to: nextLabel, wall: now() });
        }
    }

    log.push({ event: "done", wall: now() });
    return { log, errors, stepLabels };
}
"""


@dataclass
class LockstepResult:
    log: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    step_labels_observed: list[dict] = field(default_factory=list)
    total_runtime_s: float = 0.0


async def run_lockstep_in_browser(
    html_path: Path,
    steps: list[StepAudio],
    headless: bool = True,
    timeout: float = 300.0,
) -> LockstepResult:
    """Drive the lockstep protocol in a real Playwright browser.

    Loads the animation HTML, seeks to each step label in turn, plays the
    pre-synthesized audio, then tweens to the next label and waits. Captures
    every wall-clock event so we can compute drift offline.
    """
    from playwright.async_api import async_playwright

    file_url = "file:///" + str(html_path.resolve()).replace("\\", "/")
    page_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on(
                "console",
                lambda m: page_errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" else None,
            )

            await page.goto(file_url)
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            # Give the GSAP timeline a tick to construct
            await asyncio.sleep(0.5)

            payload = {
                "steps": [
                    {
                        "label": s.label,
                        "audio": s.audio_b64,
                        "duration": s.duration_s,
                    }
                    for s in steps
                ],
            }

            t0 = time.time()
            result = await asyncio.wait_for(
                page.evaluate(LOCKSTEP_RUNNER_JS, payload),
                timeout=timeout,
            )
            runtime = time.time() - t0
        finally:
            await browser.close()

    return LockstepResult(
        log=result.get("log", []),
        errors=result.get("errors", []),
        page_errors=page_errors,
        step_labels_observed=result.get("stepLabels", []),
        total_runtime_s=runtime,
    )


# ── Drift metrics ───

def compute_drift(steps: list[StepAudio], result: LockstepResult) -> dict:
    """Compute per-step drift between expected and actual sync timing.

    For each step, expected_end = (sum of prior actual durations) +
    seek_overhead + audio_duration. Actual_end is the wall time of the
    `speak_end` event. Drift = actual - expected, in milliseconds.
    """
    log = result.log
    speak_starts: dict[str, float] = {}
    speak_actuals: dict[str, float] = {}
    seek_starts: dict[str, float] = {}
    seek_ends: dict[str, float] = {}
    animate_durs: dict[str, float] = {}

    for i, e in enumerate(log):
        evt = e.get("event")
        step = e.get("step") or e.get("from") or ""
        if evt == "seek_start":
            seek_starts[step] = e.get("wall", 0)
        elif evt == "seek_end":
            seek_ends[step] = e.get("wall", 0)
        elif evt == "speak_start":
            speak_starts[step] = e.get("wall", 0)
        elif evt == "speak_end":
            speak_actuals[step] = e.get("actual_dur", 0)
        elif evt == "animate_start":
            for j in range(i + 1, len(log)):
                if log[j].get("event") == "animate_end":
                    animate_durs[step] = log[j].get("wall", 0) - e.get("wall", 0)
                    break

    per_step: list[dict] = []
    max_drift_ms = 0.0
    drifts_ms: list[float] = []

    for s in steps:
        actual_speech = speak_actuals.get(s.label, 0)
        expected_speech = s.duration_s
        speech_drift_ms = (actual_speech - expected_speech) * 1000
        seek_overhead_ms = (
            (seek_ends.get(s.label, 0) - seek_starts.get(s.label, 0)) * 1000
        )
        per_step.append({
            "label": s.label,
            "expected_speech_s": round(expected_speech, 3),
            "actual_speech_s": round(actual_speech, 3),
            "speech_drift_ms": round(speech_drift_ms, 1),
            "seek_overhead_ms": round(seek_overhead_ms, 1),
            "animate_to_next_s": round(animate_durs.get(s.label, 0), 3),
            "cache_hit": s.cache_hit,
        })
        drifts_ms.append(abs(speech_drift_ms))
        max_drift_ms = max(max_drift_ms, abs(speech_drift_ms))

    drifts_ms.sort()
    p95 = drifts_ms[int(0.95 * len(drifts_ms))] if drifts_ms else 0.0

    return {
        "per_step": per_step,
        "max_drift_ms": round(max_drift_ms, 1),
        "p95_drift_ms": round(p95, 1),
        "total_runtime_s": round(result.total_runtime_s, 2),
        "page_errors": result.page_errors,
        "lockstep_errors": result.errors,
        "labels_observed_count": len(result.step_labels_observed),
    }


# ── Frame storyboard helpers ───

def load_lesson_plan(path: Path) -> dict:
    """Load a v4 lesson_plan.json file."""
    return json.loads(path.read_text(encoding="utf-8"))


def build_step_pairs(
    frame: dict,
    gsap_labels: list[str],
    narration_override: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Match GSAP labels in the rendered HTML to planner narration text.

    Priority per label:
      1. `narration_override[label]` (CLI flag)
      2. `frame.steps[i].narration_spoken` matched by label
      3. empty string (silent step)
    """
    by_label: dict[str, str] = {}
    for s in frame.get("steps") or []:
        if not isinstance(s, dict):
            continue
        label = (s.get("label") or "").strip()
        text = (s.get("narration_spoken") or s.get("narration") or "").strip()
        if label and text:
            by_label[label] = text

    pairs: list[tuple[str, str]] = []
    for label in gsap_labels:
        text = ""
        if narration_override and label in narration_override:
            text = narration_override[label]
        elif label in by_label:
            text = by_label[label]
        pairs.append((label, text))
    return pairs
