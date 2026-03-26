"""Animation quality review using Pollinations Gemini vision.

Extracts frames from rendered MP4, sends to gemini-fast for visual QA,
returns issues and a quality score. If score < threshold, the animation
should be regenerated with the feedback.
"""

import asyncio
import base64
import logging
import os
import subprocess
import sys

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """\
You are reviewing a Manim animation for an AI education platform. \
You have BOTH the rendered video frames AND the Manim Python code that generated them. \
Use the code to understand what SHOULD happen, and the frames to see what ACTUALLY happened.

These frames are from a VIDEO — elements may be mid-transition in early frames \
(e.g., title writing animation). Judge the FINAL state, not mid-animation frames.

## What this animation should show
Type: {animation_type}
Description: {description}

## The Manim code that generated this animation
```python
{manim_code}
```

## Review these {num_frames} frames (extracted at 25%, 50%, 75%, 90% of the video)

Evaluate:
1. LAYOUT: Is the title at top? Main visual centered and large? Labels at corners/edges \
(NOT overlapping the main visual)? Check the code — are elements positioned with \
to_edge()/to_corner() or incorrectly at ORIGIN/center?
2. VISIBILITY: Is the main content (image/graph/diagram) clearly visible? Not too small, \
not blurry, not off-screen? Check if ImageMobject height is appropriate.
3. TEXT: Are all labels readable? Any garbled characters, white boxes, overlapping text? \
Check if code uses forbidden LaTeX classes (MathTex, Tex, DecimalNumber).
4. CONTENT: Does the animation match the description? Does it show the concept correctly? \
Check if the code logic (noise calculation, data loading, etc.) is mathematically correct.
5. DATA: If it should show real data (MNIST digit, etc.), is it visible and recognizable? \
Check if the code loads the prepared data files or generates synthetic garbage.
6. CODE BUGS: Any obvious Python bugs that would cause visual glitches? Off-by-one errors, \
wrong color values, elements created but never added to scene?

Respond in this EXACT format:
SCORE: [1-10]
ISSUES:
- [issue description] (LINE: [line number or "N/A"])
- [issue description] (LINE: [line number or "N/A"])
VERDICT: [PASS if score >= 6, REGENERATE if score < 6]
FEEDBACK: [If REGENERATE, specific code-level instructions: "Change line X to Y", \
"Move the label from ORIGIN to to_corner(DL)", etc.]"""


async def review_animation(
    video_path: str,
    animation_type: str,
    description: str,
    manim_code: str = "",
    num_frames: int = 4,
) -> dict:
    """Review a rendered animation video using Pollinations gemini-fast.

    Args:
        video_path: Path to the rendered MP4.
        animation_type: The animation type (data_animation, equation_reveal, etc.)
        description: What the animation should show.
        manim_code: The Python code that generated the animation.
        num_frames: Number of frames to extract for review.

    Returns:
        {
            "score": int (1-10),
            "issues": list[str],
            "verdict": "PASS" | "REGENERATE",
            "feedback": str,
            "raw_review": str,
        }
    """
    settings = get_settings()

    if not os.path.exists(video_path):
        return {
            "score": 0,
            "issues": ["Video file not found"],
            "verdict": "REGENERATE",
            "feedback": "Video file does not exist",
            "raw_review": "",
        }

    # Extract frames at equal intervals
    frames_b64 = await _extract_frames(video_path, num_frames)
    if not frames_b64:
        return {
            "score": 0,
            "issues": ["Could not extract frames from video"],
            "verdict": "REGENERATE",
            "feedback": "FFmpeg frame extraction failed",
            "raw_review": "",
        }

    # Build the multimodal message
    # Truncate code to ~3000 chars to stay within token limits
    code_for_review = manim_code[:3000] if manim_code else "Code not available."
    prompt_text = REVIEW_PROMPT.format(
        animation_type=animation_type,
        description=description[:300],
        manim_code=code_for_review,
        num_frames=len(frames_b64),
    )

    content = [{"type": "text", "text": prompt_text}]
    for b64 in frames_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })

    # Call Pollinations gemini-fast with vision
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://gen.pollinations.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.pollinations_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gemini-fast",
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": 500,
                },
            )

        if r.status_code != 200:
            logger.warning(f"Review API error: {r.status_code}")
            return {
                "score": 5,
                "issues": [f"Review API returned {r.status_code}"],
                "verdict": "PASS",
                "feedback": "",
                "raw_review": "",
            }

        data = r.json()
        raw_review = data["choices"][0]["message"]["content"]
        return _parse_review(raw_review)

    except Exception as e:
        logger.warning(f"Animation review failed: {e}")
        return {
            "score": 5,
            "issues": [str(e)],
            "verdict": "PASS",
            "feedback": "",
            "raw_review": "",
        }


async def _extract_frames(
    video_path: str,
    num_frames: int = 4,
) -> list[str]:
    """Extract evenly-spaced frames from a video as base64 PNG strings."""
    # Get video duration first
    try:
        probe = await asyncio.create_subprocess_exec(
            _ffprobe_path(), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(probe.communicate(), timeout=10)
        duration = float(stdout.decode().strip())
    except Exception:
        duration = 20.0  # fallback guess

    # Extract frames at 25%, 50%, 75%, and 90% of duration
    # (skip very start to avoid mid-title-write frames)
    percentages = [0.25, 0.5, 0.75, 0.9][:num_frames]
    timestamps = [duration * p for p in percentages]

    import tempfile
    frames_dir = tempfile.mkdtemp()
    frames_b64 = []

    for i, ts in enumerate(timestamps):
        frame_path = os.path.join(frames_dir, f"frame_{i}.png")
        try:
            proc = await asyncio.create_subprocess_exec(
                _ffmpeg_path(), "-y", "-ss", f"{ts:.2f}",
                "-i", video_path,
                "-vframes", "1", "-q:v", "2",
                frame_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)

            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                with open(frame_path, "rb") as f:
                    frames_b64.append(base64.b64encode(f.read()).decode())
        except Exception as e:
            logger.warning(f"Frame extraction at {ts:.1f}s failed: {e}")
        finally:
            try:
                os.unlink(frame_path)
            except OSError:
                pass

    try:
        os.rmdir(frames_dir)
    except OSError:
        pass

    return frames_b64


def _parse_review(raw: str) -> dict:
    """Parse the structured review response."""
    result = {
        "score": 5,
        "issues": [],
        "verdict": "PASS",
        "feedback": "",
        "raw_review": raw,
    }

    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                result["score"] = int(line.split(":")[1].strip().split("/")[0].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("- ") and result["issues"] is not None:
            result["issues"].append(line[2:].strip())
        elif line.startswith("FEEDBACK:"):
            result["feedback"] = line.split(":", 1)[1].strip()

    # Determine verdict from SCORE, not LLM text (LLM often contradicts itself)
    result["verdict"] = "PASS" if result["score"] >= 6 else "REGENERATE"

    return result


def _ffmpeg_path() -> str:
    """Find ffmpeg executable."""
    # Try system PATH first
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Common Windows locations
    for candidate in [
        r"C:\Users\aswin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return "ffmpeg"


def _ffprobe_path() -> str:
    """Find ffprobe executable."""
    import shutil
    path = shutil.which("ffprobe")
    if path:
        return path
    for candidate in [
        r"C:\Users\aswin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffprobe.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return "ffprobe"
