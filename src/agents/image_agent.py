import os
import time
import random
import requests
from pathlib import Path
from urllib.parse import quote
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Negative prompt — appended to every request to steer away from bad outputs
_NEGATIVE = (
    "text, watermark, logo, caption, subtitle, words, letters, blurry, "
    "low quality, ugly, deformed, cartoon, anime, drawing, painting, "
    "cropped, oversaturated, noise, grain"
)

# Fixed seeds per session for reproducibility within a run
_SEEDS = [42, 137, 256, 512, 1024, 2048, 4096, 8192]


class ImageAgent:
    def __init__(self, settings: dict):
        self.visual_style = settings["channel"]["visual_style"]
        self.width = 1080
        self.height = 1920
        self.timeout = 120
        self.max_retries = 4

    def _build_url(self, query: str, seed: int | None = None) -> str:
        """
        Build a Pollinations.ai URL with style injection, negative prompt,
        and an optional seed for deterministic output.
        """
        full_prompt = (
            f"{query}, {self.visual_style}, "
            "8K resolution, professional photography, award winning"
        )
        encoded_prompt = quote(full_prompt)
        encoded_negative = quote(_NEGATIVE)

        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={self.width}&height={self.height}"
            f"&nologo=true&enhance=true&safe=true"
            f"&negative={encoded_negative}"
        )
        if seed is not None:
            url += f"&seed={seed}"
        return url

    def _download(self, url: str, save_path: str, attempt_label: str = "") -> bool:
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, timeout=self.timeout, stream=True)
                if resp.status_code == 200 and len(resp.content) > 10_000:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    logger.info(f"  ✓ Image saved ({len(resp.content)//1024}KB) {attempt_label}")
                    return True
                else:
                    logger.warning(f"  ✗ Bad response {resp.status_code}, attempt {attempt+1}")
            except Exception as e:
                logger.warning(f"  ✗ Download attempt {attempt+1} failed: {e}")
                time.sleep(5 + attempt * 3)
        return False

    def generate_all(self, script: dict, workspace: Path) -> list:
        """Generate one image per scene. Returns list of local file paths."""
        queries = script.get("image_queries", [])
        image_paths = []

        for i, query in enumerate(queries):
            save_path = str(workspace / f"image_{i:02d}.jpg")
            seed = _SEEDS[i % len(_SEEDS)]

            logger.info(f"\n🖼  Image {i+1}/{len(queries)}: {query[:70]}...")

            # Primary attempt — full quality with seed
            url = self._build_url(query, seed=seed)
            success = self._download(url, save_path, attempt_label=f"[scene {i+1}]")

            if not success:
                # Fallback 1 — strip style modifiers, keep core subject
                core_query = query.split(",")[0].strip()
                logger.warning(f"  ↩ Fallback 1: simplified prompt '{core_query}'")
                fallback_url = self._build_url(core_query, seed=seed + 1)
                success = self._download(fallback_url, save_path, attempt_label="[fallback-1]")

            if not success:
                # Fallback 2 — random seed, minimal prompt
                logger.warning(f"  ↩ Fallback 2: random seed")
                fallback_url = self._build_url(core_query, seed=random.randint(1, 99999))
                success = self._download(fallback_url, save_path, attempt_label="[fallback-2]")

            if success:
                image_paths.append(save_path)
            else:
                logger.error(f"  ⚠ Image {i+1} failed all attempts — skipping.")

        return image_paths
