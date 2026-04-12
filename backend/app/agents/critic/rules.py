"""Pure-Python deterministic critic rules for the visual-first classroom.

These rules are the cheapest gate — they run in microseconds, never hit a
network, and catch the unambiguous "this violates the spec" cases:

  * Speech style: sentence length, rhetorical questions, pause markers,
    LaTeX leaks, banned generic-tutor phrases.
  * Storyboard structure: minimum frame count, frame duration bounds,
    interaction cadence, per-frame step count.
  * Frame sync reports: per-step audio/animation drift, total duration.

The rules are intentionally subject-agnostic — they enforce the *form*
of a 3b1b-style lesson (which works for any topic) without prescribing
the *content* (which differs per subject).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal


# ── Tunable thresholds (all configurable from one place) ──

MIN_FRAMES_PER_LESSON = 15
MIN_INTERACTIONS_PER_LESSON = 4
MIN_TOTAL_LESSON_SECONDS = 1500          # 25 minutes
MIN_FRAME_SECONDS = 30
MAX_FRAME_SECONDS = 75
MIN_STEPS_PER_FRAME = 3
MAX_STEPS_PER_FRAME = 8
MAX_SENTENCE_WORDS = 16                  # avg target ≤ 14, hard cap 16
RHETORICAL_QUESTION_EVERY_N_STEPS = 3    # at least 1 per N-step window
MAX_STEP_DRIFT_MS = 150                  # per-step audio/anim drift cap

# Banned generic-tutor phrases — 3b1b speech is specific, not filler
BANNED_PHRASES = (
    "in this video",
    "in this lesson",
    "let us ",
    "let's just ",
    "it is important to note",
    "as you can see",
    "as we can see",
    "kind of like",
    "really cool",
    "super cool",
    "pretty cool",
    "amazing thing",
    "now, let me explain",
    "let me explain",
    "today we will learn",
    "today we are going to",
)

# Banned openers (first ~30 chars of a step's narration)
BANNED_OPENERS = (
    "look at",
    "notice how",
    "in this video",
    "let us",
    "it is important",
    "today we",
    "welcome",
)

# LaTeX / notation leak patterns — narration must be spoken English only
LATEX_LEAK_PATTERNS = (
    re.compile(r"\\[a-zA-Z]+"),          # \beta, \frac, etc
    re.compile(r"\$[^$]+\$"),            # $x$
    re.compile(r"\b[a-zA-Z]_[a-zA-Z0-9]"),  # x_t, beta_t (underscore subscripts)
    re.compile(r"\^[0-9{]"),             # x^2, x^{...}
)


# ── Data classes ──


Severity = Literal["hard", "soft"]


@dataclass
class Violation:
    """A single critic finding.

    Hard violations block; soft violations are advisory and reported.
    """
    code: str
    message: str
    severity: Severity = "hard"
    location: str = ""           # frame_id, step label, etc.

    def __str__(self) -> str:
        loc = f" [{self.location}]" if self.location else ""
        return f"{self.severity.upper()} {self.code}{loc}: {self.message}"


@dataclass
class CheckResult:
    """Aggregated rule output."""
    violations: list[Violation] = field(default_factory=list)

    @property
    def hard(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "hard"]

    @property
    def soft(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "soft"]

    @property
    def passed(self) -> bool:
        return len(self.hard) == 0

    def add(self, v: Violation) -> None:
        self.violations.append(v)


# ── Helpers ──


def _split_sentences(text: str) -> list[str]:
    """Approximate sentence split — good enough for length checks."""
    if not text:
        return []
    # Treat ... and em-dash as legal pause markers, not sentence breaks
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))


def _has_rhetorical_question(text: str) -> bool:
    """A '?' anywhere counts. We trust planners to phrase real questions."""
    return "?" in text


def _has_pause_marker(text: str) -> bool:
    """Pauses are signalled by '...' or em-dash — Piper honors them."""
    return "..." in text or "—" in text or " - " in text


def _is_banned_opener(text: str) -> str | None:
    head = text.lower().strip()[:40]
    for phrase in BANNED_OPENERS:
        if head.startswith(phrase):
            return phrase
    return None


def _find_banned_phrase(text: str) -> str | None:
    lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            return phrase
    return None


def _find_latex_leak(text: str) -> str | None:
    for pat in LATEX_LEAK_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


# ── Public checks ──


def check_speech_voice(text: str, location: str = "") -> CheckResult:
    """Check that a single span of narration follows the 3b1b voice spec.

    Hard violations: latex leaks, banned phrases, banned openers,
    runaway sentence length.
    Soft violations: missing pause markers, suspiciously low sentence count.
    """
    out = CheckResult()
    if not text or not text.strip():
        out.add(Violation("EMPTY_NARRATION", "narration is empty",
                          severity="hard", location=location))
        return out

    # 1. LaTeX / notation leaks
    leak = _find_latex_leak(text)
    if leak:
        out.add(Violation(
            "LATEX_LEAK",
            f"narration contains math notation that won't read aloud: {leak!r}",
            severity="hard", location=location,
        ))

    # 2. Banned openers
    opener = _is_banned_opener(text)
    if opener:
        out.add(Violation(
            "BANNED_OPENER",
            f"opens with generic tutor phrase {opener!r} — be specific",
            severity="hard", location=location,
        ))

    # 3. Banned phrases (anywhere)
    banned = _find_banned_phrase(text)
    if banned:
        out.add(Violation(
            "BANNED_PHRASE",
            f"contains generic-tutor filler {banned!r}",
            severity="hard", location=location,
        ))

    # 4. Sentence length
    sentences = _split_sentences(text)
    if not sentences:
        out.add(Violation("NO_SENTENCES", "no recognisable sentences",
                          severity="hard", location=location))
        return out

    word_counts = [_word_count(s) for s in sentences]
    avg = sum(word_counts) / len(word_counts)
    long_sentences = [s for s, w in zip(sentences, word_counts) if w > MAX_SENTENCE_WORDS]
    if long_sentences:
        out.add(Violation(
            "SENTENCE_TOO_LONG",
            f"{len(long_sentences)} sentence(s) over {MAX_SENTENCE_WORDS} words "
            f"(longest {max(word_counts)} words). Break them up.",
            severity="hard", location=location,
        ))
    if avg > 14:
        out.add(Violation(
            "AVG_SENTENCE_LENGTH",
            f"average sentence length {avg:.1f} > 14 words. "
            "3b1b voice is short and direct.",
            severity="soft", location=location,
        ))

    # 5. Pause markers — soft, but we want them
    if not _has_pause_marker(text):
        out.add(Violation(
            "NO_PAUSE_MARKER",
            "no '...' or em-dash. Add a deliberate pause for emphasis.",
            severity="soft", location=location,
        ))

    return out


def check_storyboard(lesson: dict) -> CheckResult:
    """Check a v4 lesson storyboard against pedagogical hard constraints.

    `lesson` is the dict returned by Course Planner v4: keys include
    `frames` (list[dict]), `total_frames`, `total_interactions`,
    `opening_hook`, `closing_summary`. Each frame has `frame_id`,
    `estimated_seconds`, `steps` (list[dict]), `interaction`,
    `narration_spoken`, `visual_type`.
    """
    out = CheckResult()
    frames = lesson.get("frames") or []
    lesson_id = lesson.get("lesson_id", "?")

    # 1. Frame count
    if len(frames) < MIN_FRAMES_PER_LESSON:
        out.add(Violation(
            "TOO_FEW_FRAMES",
            f"{len(frames)} frames < required {MIN_FRAMES_PER_LESSON}",
            severity="hard", location=lesson_id,
        ))

    # 2. Total duration
    total_seconds = sum(int(f.get("estimated_seconds", 0)) for f in frames)
    if total_seconds < MIN_TOTAL_LESSON_SECONDS:
        out.add(Violation(
            "LESSON_TOO_SHORT",
            f"{total_seconds}s < {MIN_TOTAL_LESSON_SECONDS}s "
            f"({total_seconds // 60}min < {MIN_TOTAL_LESSON_SECONDS // 60}min)",
            severity="hard", location=lesson_id,
        ))

    # 3. Interaction count
    interactions = sum(1 for f in frames if f.get("interaction"))
    if interactions < MIN_INTERACTIONS_PER_LESSON:
        out.add(Violation(
            "TOO_FEW_INTERACTIONS",
            f"{interactions} interactions < required {MIN_INTERACTIONS_PER_LESSON}",
            severity="hard", location=lesson_id,
        ))

    # 4. Per-frame checks
    for f in frames:
        fid = f.get("frame_id", "?")

        # 4a. Frame duration bounds
        secs = int(f.get("estimated_seconds", 0))
        if secs < MIN_FRAME_SECONDS:
            out.add(Violation(
                "FRAME_TOO_SHORT",
                f"{secs}s < {MIN_FRAME_SECONDS}s — frame is rushed",
                severity="hard", location=fid,
            ))
        elif secs > MAX_FRAME_SECONDS:
            out.add(Violation(
                "FRAME_TOO_LONG",
                f"{secs}s > {MAX_FRAME_SECONDS}s — split into multiple frames",
                severity="hard", location=fid,
            ))

        # 4b. Steps required for lockstep sync
        steps = f.get("steps") or []
        if len(steps) < MIN_STEPS_PER_FRAME:
            out.add(Violation(
                "TOO_FEW_STEPS",
                f"{len(steps)} steps < required {MIN_STEPS_PER_FRAME}. "
                "Without per-step labels the lockstep sync degrades to one blob.",
                severity="hard", location=fid,
            ))
        elif len(steps) > MAX_STEPS_PER_FRAME:
            out.add(Violation(
                "TOO_MANY_STEPS",
                f"{len(steps)} steps > {MAX_STEPS_PER_FRAME} — split the frame",
                severity="soft", location=fid,
            ))

        # 4c. Per-step narration voice checks (only if narration is present)
        for i, s in enumerate(steps):
            step_loc = f"{fid}.{s.get('label', f'step{i}')}"
            spoken = (s.get("narration_spoken") or s.get("narration") or "").strip()
            if not spoken:
                out.add(Violation(
                    "EMPTY_STEP_NARRATION",
                    "step has no narration_spoken — teacher will have nothing to say",
                    severity="hard", location=step_loc,
                ))
                continue
            sub = check_speech_voice(spoken, location=step_loc)
            out.violations.extend(sub.violations)

        # 4d. Frame-level narration also checked (legacy fallback path)
        frame_narration = (f.get("narration_spoken") or "").strip()
        if frame_narration and not steps:
            sub = check_speech_voice(frame_narration, location=fid)
            out.violations.extend(sub.violations)

        # 4e. Rhetorical question cadence per N-step window
        if len(steps) >= RHETORICAL_QUESTION_EVERY_N_STEPS:
            window_texts = [
                (s.get("narration_spoken") or s.get("narration") or "")
                for s in steps
            ]
            window_size = RHETORICAL_QUESTION_EVERY_N_STEPS
            for w in range(0, len(window_texts), window_size):
                chunk = " ".join(window_texts[w:w + window_size])
                if not _has_rhetorical_question(chunk):
                    out.add(Violation(
                        "NO_RHETORICAL_QUESTION",
                        f"no question mark in steps {w + 1}–{w + window_size}. "
                        "3b1b speech asks the student to think every few beats.",
                        severity="soft", location=fid,
                    ))
                    break  # one warning per frame is enough

    return out


def check_frame_sync_report(report: dict) -> CheckResult:
    """Check the per-frame report produced by scripts/sync_test.py.

    Expected shape:
        {
          "frame_id": "f01",
          "step_count": 4,
          "steps": [
              {"label": "intro", "expected_end_ms": 5800,
               "actual_end_ms": 5912, "drift_ms": 112},
              ...
          ],
          "total_seconds": 32.4,
          "page_errors": [],
        }
    """
    out = CheckResult()
    fid = report.get("frame_id", "?")

    page_errors = report.get("page_errors") or []
    if page_errors:
        out.add(Violation(
            "PAGE_ERRORS",
            f"{len(page_errors)} JS runtime errors: "
            + "; ".join(str(e)[:80] for e in page_errors[:3]),
            severity="hard", location=fid,
        ))

    steps = report.get("steps") or []
    if not steps:
        out.add(Violation(
            "NO_SYNC_STEPS",
            "frame produced no step events — animation never reached any label",
            severity="hard", location=fid,
        ))
        return out

    drifts = [abs(int(s.get("drift_ms", 0))) for s in steps]
    if drifts:
        max_drift = max(drifts)
        p95 = sorted(drifts)[int(len(drifts) * 0.95)] if len(drifts) > 1 else max_drift
        if p95 > MAX_STEP_DRIFT_MS:
            out.add(Violation(
                "DRIFT_EXCEEDED",
                f"p95 drift {p95}ms > {MAX_STEP_DRIFT_MS}ms (max {max_drift}ms)",
                severity="hard", location=fid,
            ))

    total = float(report.get("total_seconds", 0))
    if total < MIN_FRAME_SECONDS:
        out.add(Violation(
            "FRAME_RUNTIME_TOO_SHORT",
            f"frame ran for {total:.0f}s < {MIN_FRAME_SECONDS}s",
            severity="hard", location=fid,
        ))
    elif total > MAX_FRAME_SECONDS * 1.5:  # 50% slack vs storyboard
        out.add(Violation(
            "FRAME_RUNTIME_TOO_LONG",
            f"frame ran for {total:.0f}s > {int(MAX_FRAME_SECONDS * 1.5)}s",
            severity="soft", location=fid,
        ))

    return out


def check_lesson_sync_reports(reports: Iterable[dict]) -> CheckResult:
    """Aggregate sync reports for every frame in a lesson."""
    out = CheckResult()
    for r in reports:
        sub = check_frame_sync_report(r)
        out.violations.extend(sub.violations)
    return out


# ── Self-test (run as module) ──


if __name__ == "__main__":
    # Quick smoke test on the known-broken diffusion lesson 1
    import json
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "diffusion_chapter_export" / "lesson1_plan.json"
    if not path.exists():
        print(f"no test file at {path}")
        sys.exit(1)

    lesson = json.loads(path.read_text(encoding="utf-8"))
    result = check_storyboard(lesson)
    print(f"lesson: {path.name}")
    print(f"  hard violations: {len(result.hard)}")
    print(f"  soft violations: {len(result.soft)}")
    for v in result.hard[:20]:
        print(f"  {v}")
    if len(result.hard) > 20:
        print(f"  ... and {len(result.hard) - 20} more hard violations")
