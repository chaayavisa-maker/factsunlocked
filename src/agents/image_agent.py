"""
ImageAgent – fetches images from Pollinations.ai (free, no key required).
Works for both FactsUnlocked and AstroFacts.
"""

import time
import urllib.parse
import httpx
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


def generate_image(
    prompt: str,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    timeout: int = 90,
    retries: int = 3,
) -> Path:
    """
    Download an AI image from Pollinations and save to output_path.
    Returns the saved path.
    """
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true"
    )
    if seed is not None:
        url += f"&seed={seed}"

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Fetching image (attempt {attempt}): {prompt[:60]}…")
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(resp.content)
            logger.info(f"Image saved to {output_path}")
            return output_path
        except Exception as e:
            logger.warning(f"Image fetch attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(5 * attempt)

    raise RuntimeError(f"Failed to fetch image after {retries} attempts: {prompt[:60]}")


def generate_scene_images(
    scenes: list,
    workspace: Path,
    width: int = 1080,
    height: int = 1920,
) -> list:
    """
    Generate one image per scene dict (must have 'image_prompt' key).
    Returns list of Paths in same order.
    """
    paths = []
    for i, scene in enumerate(scenes):
        prompt = scene.get("image_prompt", f"cosmic abstract scene {i+1}")
        out = workspace / f"scene_{i:02d}.jpg"
        path = generate_image(prompt, out, width=width, height=height, seed=i * 42)
        paths.append(path)
    return paths
