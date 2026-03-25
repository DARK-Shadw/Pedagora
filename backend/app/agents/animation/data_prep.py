"""Prepare real data files for animation rendering.

Downloads datasets (MNIST, CIFAR, etc.) and saves sample images
to disk so the LLM-generated Manim code can load them via ImageMobject.
"""

import logging
import os
import re

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Sample face image URL (public domain, no auth needed)
SAMPLE_FACE_URL = "https://thispersondoesnotexist.com"


async def prepare_animation_data(
    data_requirements: str,
    output_dir: str,
) -> dict[str, str]:
    """Prepare real data files based on data_requirements string.

    Returns dict with file paths and metadata:
    {
        "image_path": "/abs/path/to/image.png",
        "dataset": "MNIST",
        "description": "64x64 grayscale digit '3'",
        "files": ["path1.png", "path2.png", ...]  # for multi-image
    }
    """
    os.makedirs(output_dir, exist_ok=True)
    req = data_requirements.lower().strip()

    if not req:
        return await _prepare_synthetic(output_dir, "64x64 grayscale gradient")

    if "mnist" in req:
        return await _prepare_mnist(output_dir, req)
    elif "cifar" in req:
        return await _prepare_cifar(output_dir, req)
    elif "fashion" in req:
        return await _prepare_fashion_mnist(output_dir, req)
    elif "face" in req or "celeb" in req or "person" in req:
        return await _prepare_face(output_dir)
    elif "video" in req or "frame" in req or "clip" in req:
        return await _prepare_video_frames(output_dir, req)
    elif "noise" in req or "random" in req:
        return await _prepare_noise(output_dir, req)
    else:
        return await _prepare_synthetic(output_dir, req)


def _parse_resolution(req: str) -> tuple[int, int]:
    """Extract resolution from data requirements string.

    Always outputs at least 256x256 for visual quality — small images
    get upscaled with nearest-neighbor to stay crisp.
    """
    match = re.search(r"(\d+)\s*x\s*(\d+)", req)
    if match:
        w, h = int(match.group(1)), int(match.group(2))
        # Upscale small images for visual quality in 1080p animations
        if w < 256:
            scale = 256 // w
            w, h = w * scale, h * scale
        return w, h
    return 256, 256


def _parse_digit(req: str) -> int | None:
    """Extract target digit from requirements like 'digit 3' or 'digit \"7\"'."""
    match = re.search(r"digit\s*['\"]?(\d)['\"]?", req)
    if match:
        return int(match.group(1))
    return None


async def _prepare_mnist(output_dir: str, req: str) -> dict[str, str]:
    """Download MNIST and save sample digit(s) as PNG."""
    try:
        from torchvision.datasets import MNIST
        import torchvision.transforms as T

        ds = MNIST(
            root=os.path.join(output_dir, "_cache"),
            download=True,
            transform=T.ToTensor(),
        )

        target_digit = _parse_digit(req)
        width, height = _parse_resolution(req)

        # Find a sample of the target digit (or first image)
        img_tensor = None
        for img, label in ds:
            if target_digit is None or label == target_digit:
                img_tensor = img
                break

        if img_tensor is None:
            img_tensor = ds[0][0]

        # Convert to PIL and resize
        img_array = (img_tensor.squeeze().numpy() * 255).astype(np.uint8)
        pil_img = Image.fromarray(img_array, mode="L")
        pil_img = pil_img.resize((width, height), Image.NEAREST)

        # Save
        digit_str = str(target_digit) if target_digit is not None else "0"
        path = os.path.join(output_dir, f"mnist_{digit_str}.png")
        pil_img.save(path)

        # Also save a series with noise for diffusion animations
        files = [path]
        for i in range(8):
            noise_level = (i + 1) / 8.0
            noisy = img_array.astype(float) * (1 - noise_level) + \
                np.random.rand(*img_array.shape) * 255 * noise_level
            noisy_img = Image.fromarray(noisy.astype(np.uint8), mode="L")
            noisy_img = noisy_img.resize((width, height), Image.NEAREST)
            noisy_path = os.path.join(output_dir, f"mnist_{digit_str}_noise_{i}.png")
            noisy_img.save(noisy_path)
            files.append(noisy_path)

        logger.info(f"Prepared MNIST digit {digit_str}: {path} ({width}x{height})")
        return {
            "image_path": os.path.abspath(path),
            "dataset": "MNIST",
            "description": f"{width}x{height} grayscale digit '{digit_str}'",
            "files": [os.path.abspath(f) for f in files],
            "noisy_series": [os.path.abspath(f) for f in files[1:]],
        }

    except Exception as e:
        logger.warning(f"MNIST preparation failed: {e}, falling back to synthetic")
        return await _prepare_synthetic(output_dir, req)


async def _prepare_cifar(output_dir: str, req: str) -> dict[str, str]:
    """Download CIFAR-10 and save a sample image."""
    try:
        from torchvision.datasets import CIFAR10
        import torchvision.transforms as T

        ds = CIFAR10(
            root=os.path.join(output_dir, "_cache"),
            download=True,
            transform=T.ToTensor(),
        )

        img_tensor, label = ds[0]
        img_array = (img_tensor.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        pil_img = Image.fromarray(img_array)

        width, height = _parse_resolution(req)
        pil_img = pil_img.resize((width, height), Image.NEAREST)

        path = os.path.join(output_dir, "cifar_sample.png")
        pil_img.save(path)

        logger.info(f"Prepared CIFAR-10 sample: {path}")
        return {
            "image_path": os.path.abspath(path),
            "dataset": "CIFAR-10",
            "description": f"{width}x{height} color image (airplane)",
            "files": [os.path.abspath(path)],
        }

    except Exception as e:
        logger.warning(f"CIFAR preparation failed: {e}")
        return await _prepare_synthetic(output_dir, req)


async def _prepare_fashion_mnist(output_dir: str, req: str) -> dict[str, str]:
    """Download FashionMNIST and save a sample image."""
    try:
        from torchvision.datasets import FashionMNIST
        import torchvision.transforms as T

        ds = FashionMNIST(
            root=os.path.join(output_dir, "_cache"),
            download=True,
            transform=T.ToTensor(),
        )

        img_tensor, label = ds[0]
        img_array = (img_tensor.squeeze().numpy() * 255).astype(np.uint8)
        pil_img = Image.fromarray(img_array, mode="L")

        width, height = _parse_resolution(req)
        pil_img = pil_img.resize((width, height), Image.NEAREST)

        path = os.path.join(output_dir, "fashion_mnist_sample.png")
        pil_img.save(path)

        logger.info(f"Prepared FashionMNIST sample: {path}")
        return {
            "image_path": os.path.abspath(path),
            "dataset": "FashionMNIST",
            "description": f"{width}x{height} grayscale clothing item",
            "files": [os.path.abspath(path)],
        }

    except Exception as e:
        logger.warning(f"FashionMNIST preparation failed: {e}")
        return await _prepare_synthetic(output_dir, req)


async def _prepare_face(output_dir: str) -> dict[str, str]:
    """Download a sample face image."""
    try:
        import httpx

        path = os.path.join(output_dir, "face_sample.png")

        # Use a simple generated face (no auth needed)
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            r = await client.get(SAMPLE_FACE_URL)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                logger.info(f"Prepared face sample: {path}")
                return {
                    "image_path": os.path.abspath(path),
                    "dataset": "generated_face",
                    "description": "Generated human face image",
                    "files": [os.path.abspath(path)],
                }
    except Exception as e:
        logger.warning(f"Face download failed: {e}")

    return await _prepare_synthetic(output_dir, "128x128 color portrait placeholder")


async def _prepare_video_frames(output_dir: str, req: str) -> dict[str, str]:
    """Generate synthetic video frames (moving shapes)."""
    width, height = _parse_resolution(req)
    num_frames_match = re.search(r"(\d+)\s*frame", req)
    num_frames = int(num_frames_match.group(1)) if num_frames_match else 8

    files = []
    for frame_idx in range(num_frames):
        img = np.zeros((height, width, 3), dtype=np.uint8)

        # Draw a white circle moving across the frame
        cx = int(width * (frame_idx + 1) / (num_frames + 1))
        cy = height // 2
        radius = min(width, height) // 6

        y, x = np.ogrid[:height, :width]
        mask = (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2
        img[mask] = [255, 255, 255]

        pil_img = Image.fromarray(img)
        path = os.path.join(output_dir, f"frame_{frame_idx:03d}.png")
        pil_img.save(path)
        files.append(os.path.abspath(path))

    logger.info(f"Prepared {num_frames} video frames: {output_dir}")
    return {
        "image_path": files[0],
        "dataset": "synthetic_video",
        "description": f"{num_frames} frames of {width}x{height} video (white circle moving)",
        "files": files,
    }


async def _prepare_noise(output_dir: str, req: str) -> dict[str, str]:
    """Generate noise images at various levels."""
    width, height = _parse_resolution(req)

    files = []
    for i, noise_level in enumerate([0.0, 0.25, 0.5, 0.75, 1.0]):
        if noise_level == 0:
            img_array = np.ones((height, width), dtype=np.uint8) * 128
        else:
            img_array = (np.random.rand(height, width) * 255 * noise_level).astype(np.uint8)
        pil_img = Image.fromarray(img_array, mode="L")
        path = os.path.join(output_dir, f"noise_level_{i}.png")
        pil_img.save(path)
        files.append(os.path.abspath(path))

    return {
        "image_path": files[0],
        "dataset": "noise_series",
        "description": f"5 images at noise levels 0%, 25%, 50%, 75%, 100%",
        "files": files,
    }


async def _prepare_synthetic(output_dir: str, req: str) -> dict[str, str]:
    """Generate a synthetic pattern image (checkerboard, gradient, etc.)."""
    width, height = _parse_resolution(req)

    if "checker" in req:
        img = np.zeros((height, width), dtype=np.uint8)
        block = max(width // 8, 4)
        for i in range(height):
            for j in range(width):
                if (i // block + j // block) % 2 == 0:
                    img[i, j] = 255
    elif "gradient" in req:
        img = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    else:
        # Simple geometric pattern
        img = np.zeros((height, width), dtype=np.uint8)
        # White rectangle in center
        margin = max(width // 8, 4)
        img[margin:-margin, margin:-margin] = 200

    pil_img = Image.fromarray(img, mode="L")
    path = os.path.join(output_dir, "synthetic.png")
    pil_img.save(path)

    logger.info(f"Prepared synthetic image: {path}")
    return {
        "image_path": os.path.abspath(path),
        "dataset": "synthetic",
        "description": f"{width}x{height} synthetic pattern",
        "files": [os.path.abspath(path)],
    }
