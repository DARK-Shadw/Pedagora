"""Sync test harness CLI — full lesson or single frame.

Drives the lockstep protocol against a real animation HTML file with the
planner's narration text, captures wall-clock timings inside Playwright,
and writes a per-frame JSON drift report.

Usage:
    # Single frame from the diffusion lesson 1 plan
    python scripts/sync_test.py \
        --plan backend/diffusion_chapter_export/lesson1_plan.json \
        --visuals-dir backend/generated_visuals \
        --frame f01

    # All frames in a lesson
    python scripts/sync_test.py \
        --plan backend/diffusion_chapter_export/lesson1_plan.json \
        --visuals-dir backend/generated_visuals

    # Override narration for legacy frames with empty steps[]
    python scripts/sync_test.py --plan ... --frame f01 \
        --narration-override sync_tests/fixtures/f01_narration.json

Reports are written to `sync_tests/reports/<lesson_id>/<frame_id>.json`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Make `sync_tests/_common.py` importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from sync_tests._common import (  # noqa: E402
    build_step_pairs,
    compute_drift,
    extract_gsap_labels,
    load_lesson_plan,
    run_lockstep_in_browser,
    synth_steps,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _resolve_frames(plan: dict, frame_arg: str | None) -> list[dict]:
    """Pull the frame list out of either a v4 lesson_plan or wrapped doc."""
    frames: list[dict] = []
    if "frames" in plan:
        frames = plan["frames"]
    elif "lesson_plans" in plan:
        # course_plans row format: pick the first lesson
        first = next(iter(plan["lesson_plans"].values()), {})
        frames = first.get("frames", [])
    if frame_arg:
        frames = [f for f in frames if f.get("frame_id") == frame_arg]
    return frames


async def run_one_frame(
    frame: dict,
    visuals_dir: Path,
    output_dir: Path,
    lesson_id: str,
    narration_override: dict[str, str] | None,
    headless: bool,
) -> dict:
    frame_id = frame.get("frame_id", "?")
    html_path = visuals_dir / f"{frame_id}.html"
    if not html_path.exists():
        logger.error(f"[{frame_id}] HTML not found at {html_path}")
        return {"frame_id": frame_id, "error": "html_missing", "path": str(html_path)}

    html = html_path.read_text(encoding="utf-8")
    gsap_labels = extract_gsap_labels(html)
    if not gsap_labels:
        logger.error(f"[{frame_id}] no GSAP labels in HTML")
        return {"frame_id": frame_id, "error": "no_gsap_labels"}

    pairs = build_step_pairs(frame, gsap_labels, narration_override)
    matched = sum(1 for _, t in pairs if t)
    logger.info(
        f"[{frame_id}] {len(gsap_labels)} labels, {matched} narration matches"
    )

    if matched == 0:
        logger.warning(f"[{frame_id}] no narration matched any GSAP label — silent run")

    steps = await synth_steps(pairs)
    total_audio = sum(s.duration_s for s in steps)
    logger.info(f"[{frame_id}] synth ok, total audio {total_audio:.1f}s")

    result = await run_lockstep_in_browser(html_path, steps, headless=headless)
    drift = compute_drift(steps, result)

    report = {
        "frame_id": frame_id,
        "lesson_id": lesson_id,
        "html_path": str(html_path),
        "label_count": len(gsap_labels),
        "narration_matched": matched,
        "total_planned_audio_s": round(total_audio, 2),
        "drift": drift,
        "step_audio": [
            {
                "label": s.label,
                "text": s.text,
                "duration_s": round(s.duration_s, 3),
                "synth_seconds": round(s.synth_seconds, 3),
                "cache_hit": s.cache_hit,
            }
            for s in steps
        ],
    }

    out_path = output_dir / lesson_id / f"{frame_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"[{frame_id}] report written: max_drift={drift['max_drift_ms']}ms, "
        f"p95={drift['p95_drift_ms']}ms, runtime={drift['total_runtime_s']}s "
        f"-> {out_path}"
    )
    return report


async def main_async(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    if not plan_path.exists():
        logger.error(f"plan file not found: {plan_path}")
        return 2

    visuals_dir = Path(args.visuals_dir)
    if not visuals_dir.exists():
        logger.error(f"visuals dir not found: {visuals_dir}")
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = load_lesson_plan(plan_path)
    frames = _resolve_frames(plan, args.frame)
    if not frames:
        logger.error(f"no frames matched (frame={args.frame})")
        return 2

    narration_override: dict[str, str] | None = None
    if args.narration_override:
        narration_override = json.loads(
            Path(args.narration_override).read_text(encoding="utf-8")
        )

    lesson_id = plan.get("lesson_id") or args.lesson_id or "lesson"

    reports: list[dict] = []
    for frame in frames:
        try:
            r = await run_one_frame(
                frame=frame,
                visuals_dir=visuals_dir,
                output_dir=output_dir,
                lesson_id=lesson_id,
                narration_override=narration_override,
                headless=not args.headed,
            )
            reports.append(r)
        except Exception as e:
            logger.exception(f"frame failed: {e}")
            reports.append({"frame_id": frame.get("frame_id", "?"), "error": str(e)})

    # Summary
    summary = {
        "lesson_id": lesson_id,
        "frames_run": len(reports),
        "frames_with_errors": sum(1 for r in reports if r.get("error") or r.get("drift", {}).get("page_errors")),
        "max_drift_ms": max(
            (r.get("drift", {}).get("max_drift_ms", 0) for r in reports if "drift" in r),
            default=0,
        ),
        "frames": [
            {
                "frame_id": r.get("frame_id"),
                "max_drift_ms": r.get("drift", {}).get("max_drift_ms"),
                "p95_drift_ms": r.get("drift", {}).get("p95_drift_ms"),
                "page_errors": len(r.get("drift", {}).get("page_errors", [])),
                "error": r.get("error"),
            }
            for r in reports
        ],
    }
    summary_path = output_dir / lesson_id / "_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"DONE: {summary['frames_run']} frames, "
        f"{summary['frames_with_errors']} with errors, "
        f"max drift = {summary['max_drift_ms']}ms"
    )
    logger.info(f"summary -> {summary_path}")

    return 0 if summary["frames_with_errors"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Pedagora sync test harness")
    parser.add_argument("--plan", required=True, help="Path to lesson_plan.json (v4 format)")
    parser.add_argument("--visuals-dir", required=True, help="Directory containing <frame_id>.html files")
    parser.add_argument("--frame", default=None, help="Restrict to a single frame id (e.g. f01)")
    parser.add_argument("--lesson-id", default=None, help="Override lesson_id used in report path")
    parser.add_argument(
        "--narration-override",
        default=None,
        help="JSON file mapping {label: narration_text} for legacy/empty plans",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("sync_tests") / "reports"),
        help="Where to write JSON reports (default: sync_tests/reports)",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
