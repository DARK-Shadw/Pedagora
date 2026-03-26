"""Render Manim scenes to MP4 via subprocess."""

import asyncio
import logging
import os
import sys
import tempfile
import time

logger = logging.getLogger(__name__)


async def render_manim_scene(
    code: str,
    output_dir: str,
    quality: str = "l",
    timeout: int = 300,
) -> tuple[str | None, str | None]:
    """Render a Manim scene and return (output_path, error).

    Returns (path_to_mp4, None) on success.
    Returns (None, error_message) on failure.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Write code to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", dir=output_dir, delete=False, encoding="utf-8",
    ) as f:
        f.write(code)
        scene_file = f.name

    scene_basename = os.path.splitext(os.path.basename(scene_file))[0]
    start = time.time()

    try:
        # Ensure MiKTeX binaries are in PATH for LaTeX rendering
        env = os.environ.copy()
        miktex_bin = os.path.expanduser(
            "~/AppData/Local/Programs/MiKTeX/miktex/bin/x64"
        )
        if os.path.isdir(miktex_bin) and miktex_bin not in env.get("PATH", ""):
            env["PATH"] = miktex_bin + os.pathsep + env.get("PATH", "")

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "manim", "render",
            f"-q{quality}", "--format", "mp4",
            "--media_dir", output_dir,
            scene_file, "AnimationScene",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return None, f"Render timed out after {timeout}s"

        elapsed = time.time() - start

        if proc.returncode == 0:
            # Find the output MP4
            quality_dir = {"l": "480p15", "m": "720p30", "h": "1080p60"}.get(
                quality, "480p15"
            )
            expected_path = os.path.join(
                output_dir, "videos", scene_basename,
                quality_dir, "AnimationScene.mp4",
            )

            if os.path.exists(expected_path):
                logger.info(f"Rendered in {elapsed:.1f}s: {expected_path}")
                return expected_path, None

            # Search for any MP4
            for root, _, files in os.walk(output_dir):
                for file in files:
                    if file == "AnimationScene.mp4":
                        path = os.path.join(root, file)
                        logger.info(f"Rendered in {elapsed:.1f}s: {path}")
                        return path, None

            return None, "Render succeeded but AnimationScene.mp4 not found"

        else:
            error = stderr.decode("utf-8", errors="replace")
            # Truncate to last 1500 chars (most useful part of traceback)
            if len(error) > 1500:
                error = "...\n" + error[-1500:]
            return None, error

    finally:
        try:
            os.unlink(scene_file)
        except OSError:
            pass
