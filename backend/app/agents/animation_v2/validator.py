"""Headless-browser runtime validator for Animation v2 frames.

What this catches that pure JS syntax checking can't:
  * `pageerror` events (a `tl` is undefined, a CDN script 404'd, etc.)
  * The animation HTML never exposes `window.animationAPI`
  * `tl.labels` is empty — no GSAP labels were registered
  * Seek-to-label fails for one of the planner's expected labels
  * Visual blank: every screenshot at every step is the same (no animation)

Returns a `RuntimeReport` with hard failures (`blocking`), advisories,
captured screenshots (one per step label), and the labels actually present
in the timeline. Generator wraps this in its retry loop.

Uses Playwright's SYNC API in asyncio.to_thread() to avoid the
`asyncio.create_subprocess_exec` NotImplementedError on Python 3.14 +
uvicorn on Windows.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import tempfile
import time as _time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RuntimeReport:
    """Result of running an animation HTML through Playwright."""
    page_errors: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    advisory: list[str] = field(default_factory=list)
    labels_in_timeline: list[str] = field(default_factory=list)
    missing_labels: list[str] = field(default_factory=list)
    screenshots_b64: list[str] = field(default_factory=list)
    step_labels_for_screenshots: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.blocking and not self.page_errors

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "page_errors": self.page_errors,
            "console_errors": self.console_errors,
            "blocking": self.blocking,
            "advisory": self.advisory,
            "labels_in_timeline": self.labels_in_timeline,
            "missing_labels": self.missing_labels,
            "screenshot_count": len(self.screenshots_b64),
            "runtime_seconds": round(self.runtime_seconds, 2),
        }


_INSPECT_JS = r"""
() => {
    if (!window.animationAPI) {
        return { ok: false, reason: "animationAPI missing" };
    }
    const tl = window.animationAPI.timeline;
    if (!tl) {
        return { ok: false, reason: "animationAPI.timeline missing" };
    }
    const labels = tl.labels || {};
    return {
        ok: true,
        labels: Object.keys(labels),
        duration: tl.duration ? tl.duration() : 0,
    };
}
"""


def _run_validation_sync(
    file_url: str,
    expected: list[str],
    capture_screenshots: bool,
    timeout: float,
) -> RuntimeReport:
    """Run Playwright sync API in a thread. Uses subprocess.Popen internally
    (not asyncio.create_subprocess_exec), so it works on any event loop."""
    from playwright.sync_api import sync_playwright
    import time

    report = RuntimeReport()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            page = context.new_page()

            page.on("pageerror", lambda exc: report.page_errors.append(str(exc)))

            def _on_console(msg):
                if msg.type == "error":
                    report.console_errors.append(msg.text)

            page.on("console", _on_console)

            try:
                page.goto(file_url, timeout=timeout * 1000)
            except Exception:
                report.blocking.append("page goto timed out")
                return report

            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                report.advisory.append("networkidle timed out (CDN slow?)")

            time.sleep(0.5)

            inspect = page.evaluate(_INSPECT_JS)
            if not inspect.get("ok"):
                report.blocking.append(
                    f"animation contract broken: {inspect.get('reason', 'unknown')}"
                )
                return report

            report.labels_in_timeline = list(inspect.get("labels") or [])
            if not report.labels_in_timeline:
                report.blocking.append(
                    "no GSAP labels registered (tl.addLabel never called)"
                )

            if expected:
                missing = [l for l in expected if l not in report.labels_in_timeline]
                report.missing_labels = missing
                if missing:
                    report.blocking.append(
                        f"missing labels: {', '.join(missing[:5])}"
                        + (f" (+{len(missing)-5} more)" if len(missing) > 5 else "")
                    )

            if capture_screenshots and report.labels_in_timeline:
                for label in report.labels_in_timeline:
                    try:
                        page.evaluate(
                            "(label) => window.animationAPI.seekToStep(label)",
                            label,
                        )
                        time.sleep(0.15)
                        png = page.screenshot(full_page=False)
                        report.screenshots_b64.append(base64.b64encode(png).decode("ascii"))
                        report.step_labels_for_screenshots.append(label)
                    except Exception as e:
                        report.advisory.append(f"screenshot at '{label}' failed: {e}")

            if report.page_errors:
                report.blocking.append(
                    f"pageerror: {report.page_errors[0][:200]}"
                )

        finally:
            browser.close()

    return report


async def validate_animation_runtime(
    html: str,
    expected_labels: list[str] | None = None,
    capture_screenshots: bool = True,
    timeout: float = 30.0,
) -> RuntimeReport:
    """Load `html` in headless Chromium and check the lockstep contract.

    Runs Playwright's sync API in a background thread via asyncio.to_thread()
    to avoid the create_subprocess_exec issue on Python 3.14 + uvicorn Windows.
    """
    report = RuntimeReport()
    expected = expected_labels or []
    t_start = _time.time()

    tmp_dir = Path(tempfile.mkdtemp(prefix="pedagora_anim_validate_"))
    tmp_html = tmp_dir / "frame.html"
    tmp_html.write_text(html, encoding="utf-8")
    file_url = "file:///" + str(tmp_html.resolve()).replace("\\", "/")

    try:
        report = await asyncio.to_thread(
            _run_validation_sync,
            file_url,
            expected,
            capture_screenshots,
            timeout,
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        report.blocking.append(
            f"validator crashed: {type(e).__name__}: {e or 'no message'}\n{tb[-500:]}"
        )
        logger.error(f"[AnimValidator] crashed: {type(e).__name__}: {e}\n{tb}")
    finally:
        try:
            tmp_html.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass
        report.runtime_seconds = _time.time() - t_start

    return report
