"""TEST 2: Extract step timing from generated animations.

We need to know:
- What labels exist in each animation
- The absolute time of each label (in animation seconds)
- Total animation duration
- Time gap between consecutive steps

This drives the sync strategy: speech for step N must finish before
step N+1 is reached, OR animation pauses until speech catches up.
"""

import asyncio
import json
import os
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

ANIM_DIR = os.path.join(
    os.path.dirname(__file__), "..", "backend", "generated_visuals"
)


def extract_labels_regex(html: str) -> list[str]:
    """Quick regex extraction (label names only, no times)."""
    pattern = r"tl\.addLabel\(['\"]([^'\"]+)['\"]"
    return re.findall(pattern, html)


async def extract_runtime_timing(html_path: str) -> dict:
    """Open the file in headless Chromium, run the timeline, get real timings."""
    file_url = "file:///" + os.path.abspath(html_path).replace("\\", "/")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        await page.goto(file_url)
        # Wait for animation to be set up
        await asyncio.sleep(1.5)

        # Pause it so we can inspect
        try:
            await page.evaluate("window.animationAPI && window.animationAPI.pause()")
        except Exception:
            pass

        info = await page.evaluate("""
            () => {
                if (!window.animationAPI || !window.animationAPI.timeline) {
                    return { error: 'no animationAPI' };
                }
                const tl = window.animationAPI.timeline;
                const labels = tl.labels || {};
                return {
                    duration: tl.duration(),
                    labels: labels,
                    label_count: Object.keys(labels).length,
                };
            }
        """)

        await browser.close()
        info["errors"] = errors
        return info


async def main():
    print("=" * 70)
    print("TEST 2: Animation timing extraction")
    print("=" * 70)

    files = sorted([f for f in os.listdir(ANIM_DIR) if f.endswith(".html") and f.startswith("f")])
    print(f"\nFound {len(files)} animation files")

    results = []
    for fname in files:
        path = os.path.join(ANIM_DIR, fname)
        print(f"\n--- {fname} ---")
        try:
            info = await extract_runtime_timing(path)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if info.get("error"):
            print(f"  ERROR: {info['error']}")
            continue

        if info.get("errors"):
            print(f"  PAGE ERRORS: {info['errors']}")

        duration = info.get("duration", 0)
        labels = info.get("labels", {})
        sorted_labels = sorted(labels.items(), key=lambda x: x[1])

        print(f"  Duration: {duration:.1f}s")
        print(f"  Steps: {len(labels)}")
        for i, (name, t) in enumerate(sorted_labels):
            next_t = sorted_labels[i + 1][1] if i + 1 < len(sorted_labels) else duration
            gap = next_t - t
            print(f"    [{t:6.2f}s] {name:30s} (segment: {gap:.1f}s)")

        results.append({
            "frame": fname,
            "duration": duration,
            "labels": dict(sorted_labels),
            "errors": info.get("errors", []),
        })

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Frame':<15} {'Duration':<10} {'Steps':<8} {'Avg gap':<10} {'Min gap':<10}")
    for r in results:
        labels = r["labels"]
        if not labels:
            continue
        times = sorted(labels.values())
        gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        if gaps:
            avg_gap = sum(gaps) / len(gaps)
            min_gap = min(gaps)
        else:
            avg_gap = min_gap = r["duration"]
        print(f"{r['frame']:<15} {r['duration']:<10.1f} {len(labels):<8} {avg_gap:<10.1f} {min_gap:<10.1f}")

    # Save to file
    out_path = os.path.join(os.path.dirname(__file__), "animation_timings.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
