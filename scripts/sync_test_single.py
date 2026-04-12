"""CI smoke test for the sync harness — runs ONE hardcoded frame end-to-end.

Lighter than `sync_test.py`: no Supabase, no flag soup, just enough to catch
regressions on every push (e.g. lockstep engine breaks, Piper segfaults,
disk cache corrupts, animation HTML drops `window.animationAPI`).

Exit codes:
    0  — passed (max drift < threshold, no page errors)
    1  — sync failure (drift over threshold or page errors)
    2  — fixture missing
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from sync_tests._common import (  # noqa: E402
    build_step_pairs,
    compute_drift,
    extract_gsap_labels,
    run_lockstep_in_browser,
    synth_steps,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Hardcoded smoke-test target — must remain stable across runs.
SMOKE_FRAME_HTML = _REPO_ROOT / "backend" / "generated_visuals" / "f01.html"
SMOKE_NARRATION = {
    "noise": "Every pixel here is just a random number.",
    "structure-emerges": "Now... structure is starting to appear.",
    "face-emerges": "And there it is — a face from random numbers.",
    "question": "So... what just happened?",
}
MAX_DRIFT_MS = 250  # CI is more lenient than the production gate (150 ms)


async def main_async() -> int:
    if not SMOKE_FRAME_HTML.exists():
        logger.error(f"smoke fixture missing: {SMOKE_FRAME_HTML}")
        return 2

    html = SMOKE_FRAME_HTML.read_text(encoding="utf-8")
    gsap_labels = extract_gsap_labels(html)
    if not gsap_labels:
        logger.error("smoke fixture has no GSAP labels")
        return 2

    fake_frame = {"steps": [], "frame_id": "smoke"}
    pairs = build_step_pairs(fake_frame, gsap_labels, narration_override=SMOKE_NARRATION)
    matched = sum(1 for _, t in pairs if t)
    if matched == 0:
        logger.error("no narration matched any GSAP label — fixture out of sync")
        return 2

    logger.info(f"smoke: {len(gsap_labels)} labels, {matched} matched")

    steps = await synth_steps(pairs)
    result = await run_lockstep_in_browser(SMOKE_FRAME_HTML, steps)
    drift = compute_drift(steps, result)

    print(json.dumps({
        "max_drift_ms": drift["max_drift_ms"],
        "p95_drift_ms": drift["p95_drift_ms"],
        "page_errors": drift["page_errors"],
        "lockstep_errors": drift["lockstep_errors"],
        "runtime_s": drift["total_runtime_s"],
    }, indent=2))

    if drift["page_errors"]:
        logger.error("smoke FAILED: page errors present")
        return 1
    if drift["max_drift_ms"] > MAX_DRIFT_MS:
        logger.error(
            f"smoke FAILED: drift {drift['max_drift_ms']}ms > {MAX_DRIFT_MS}ms threshold"
        )
        return 1

    logger.info("smoke PASSED")
    return 0


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
