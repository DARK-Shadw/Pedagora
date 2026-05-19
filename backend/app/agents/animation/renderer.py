"""Render Manim scenes to MP4 via subprocess.

Uses subprocess.Popen in asyncio.to_thread() instead of
asyncio.create_subprocess_exec() because the latter raises
NotImplementedError on Windows with uvicorn's ProactorEventLoop.

Streams stderr to parse tqdm progress in real time.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable

import asyncio

logger = logging.getLogger(__name__)

_TQDM_RE = re.compile(
    r"Animation\s+(\d+):.*?(\d+)%\|[^|]*\|\s*(\d+)/(\d+)"
)


def _render_sync(
    scene_file: str,
    output_dir: str,
    quality: str,
    timeout: int,
    use_opengl: bool,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[str | None, str | None]:
    """Synchronous Manim render via subprocess.Popen. Runs in a thread."""
    scene_basename = os.path.splitext(os.path.basename(scene_file))[0]
    start = time.time()

    env = os.environ.copy()
    miktex_bin = os.path.expanduser(
        "~/AppData/Local/Programs/MiKTeX/miktex/bin/x64"
    )
    if os.path.isdir(miktex_bin) and miktex_bin not in env.get("PATH", ""):
        env["PATH"] = miktex_bin + os.pathsep + env.get("PATH", "")

    cmd = [
        sys.executable, "-m", "manim", "render",
        f"-q{quality}", "--format", "mp4",
        "--media_dir", output_dir,
    ]
    if use_opengl:
        cmd += ["--renderer", "opengl", "--write_to_movie"]
    cmd += [scene_file, "AnimationScene"]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )

    stderr_chunks: list[str] = []

    def _drain_stderr():
        """Read stderr, split on \\r/\\n, emit tqdm progress via callback."""
        buf = ""
        while True:
            data = proc.stderr.read(512)
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            buf += text
            while "\r" in buf or "\n" in buf:
                r = buf.find("\r")
                n = buf.find("\n")
                if r == -1:
                    pos = n
                elif n == -1:
                    pos = r
                else:
                    pos = min(r, n)
                line = buf[:pos]
                buf = buf[pos + 1:]
                if not line.strip():
                    continue
                stderr_chunks.append(line)
                if progress_callback:
                    m = _TQDM_RE.search(line)
                    if m:
                        anim_num = m.group(1)
                        pct = m.group(2)
                        cur = m.group(3)
                        total = m.group(4)
                        elapsed = time.time() - start
                        progress_callback(
                            f"Manim anim {anim_num}: {pct}% "
                            f"({cur}/{total} frames, {elapsed:.0f}s elapsed)"
                        )
                    elif "error" in line.lower() or "traceback" in line.lower():
                        progress_callback(f"Manim: {line.strip()[:120]}")
                    elif line.strip().startswith("Animation"):
                        elapsed = time.time() - start
                        progress_callback(
                            f"Manim: {line.strip()[:80]} ({elapsed:.0f}s)"
                        )
        if buf.strip():
            stderr_chunks.append(buf)

    reader = threading.Thread(target=_drain_stderr, daemon=True)
    reader.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=5)
        return None, f"Render timed out after {timeout}s"

    reader.join(timeout=10)
    elapsed = time.time() - start

    if proc.returncode == 0:
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

        for root, _, files in os.walk(output_dir):
            for file in files:
                if file == "AnimationScene.mp4":
                    path = os.path.join(root, file)
                    logger.info(f"Rendered in {elapsed:.1f}s: {path}")
                    return path, None

        return None, "Render succeeded but AnimationScene.mp4 not found"

    else:
        error = "\n".join(stderr_chunks)
        if len(error) > 1500:
            error = "...\n" + error[-1500:]
        return None, error


async def render_manim_scene(
    code: str,
    output_dir: str,
    quality: str = "l",
    timeout: int = 300,
    use_opengl: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[str | None, str | None]:
    """Render a Manim scene and return (output_path, error).

    Returns (path_to_mp4, None) on success.
    Returns (None, error_message) on failure.

    Runs subprocess.Popen in asyncio.to_thread() to avoid the
    NotImplementedError from asyncio.create_subprocess_exec on Windows.

    If progress_callback is provided, it's called with tqdm progress
    strings as Manim renders each animation.
    """
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8",
    ) as f:
        f.write(code)
        scene_file = f.name

    try:
        return await asyncio.to_thread(
            _render_sync, scene_file, output_dir, quality,
            timeout, use_opengl, progress_callback,
        )
    finally:
        try:
            os.unlink(scene_file)
        except OSError:
            pass
