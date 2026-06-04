import os
import time
import random
import requests
from pathlib import Path
from urllib.parse import quote
from src.utils.logger import get_logger

logger = get_logger(__name__)

_NEGATIVE = (
    "text, watermark, logo, caption, subtitle, words, letters, blurry, "
    "low quality, ugly, deformed, cartoon, anime, drawing, painting, "
    "cropped, oversaturated, noise, grain"
)

_SEEDS = [42, 137, 256, 512, 1024, 2048, 4096, 8192]

_HEADERS = {
    "Referer": "https://pollinations.ai",
    "User-Agent": "Mozilla/5.0",
}


class ImageAgent:
    def __init__(self, settings: dict):
        self.visual_style = settings["channel"]["visual_style"]
        self.width = 1080
        self.height = 1920
        self.timeout = 120
        self.max_retries = 4
        self._token = os.getenv("POLLINATIONS_TOKEN", "")
        logger.info(
            f"Pollinations token: "
            f"{'set (' + self._token[:6] + '…)' if self._token else 'NOT SET ⚠'}"
        )

    def _build_url(self, query: str, seed: int | None = None) -> str:
        full_prompt = (
            f"{query}, {self.visual_style}, "
            "8K resolution, professional photography, award winning"
        )
        url = (
            f"https://gen.pollinations.ai/image/{quote(full_prompt)}"
            f"?width={self.width}&height={self.height}"
            f"&safe=true&negative={quote(_NEGATIVE)}"
        )
        if self._token:
            url += f"&nologo=true&enhance=true&key={self._token}"
        if seed is not None:
            url += f"&seed={seed}"
        return url

    def _backoff(self, attempt: int, base: int = 10) -> None:
        delay = base * (2 ** attempt)
        logger.info(f"  ⏳ Waiting {delay}s before retry…")
        time.sleep(delay)

    def _download(self, url: str, save_path: str, attempt_label: str = "") -> bool:
        balance_wait_done = False   # wait at most 1 hour per image for balance recharge

        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=self.timeout, stream=True)
                if resp.status_code == 200 and len(resp.content) > 10_000:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    logger.info(f"  ✓ Image saved ({len(resp.content)//1024}KB) {attempt_label}")
                    return True

                body_hint = ""
                try:
                    body_hint = f" — {resp.text[:200]}"
                except Exception:
                    pass
                logger.warning(
                    f"  ✗ Bad response {resp.status_code}, attempt {attempt+1}{body_hint}"
                )

                if resp.status_code == 402:
                    try:
                        msg = resp.json().get("error", {}).get("message", "")
                    except Exception:
                        msg = ""

                    if "Insufficient balance" in msg and not balance_wait_done:
                        logger.warning(
                            "  💰 Insufficient balance — waiting 1 hour for credits to recharge…"
                        )
                        time.sleep(3600)
                        balance_wait_done = True
                        continue   # retry immediately after the wait, no extra backoff

                    # queue full or other 402 — exponential backoff
                    self._backoff(attempt, base=15)
                else:
                    self._backoff(attempt, base=5)

            except Exception as e:
                logger.warning(f"  ✗ Download attempt {attempt+1} failed: {e}")
                self._backoff(attempt)
        return False

    def generate_all(self, script: dict, workspace: Path) -> list:
        queries = script.get("image_queries", [])
        image_paths = []

        for i, query in enumerate(queries):
            if i > 0:
                time.sleep(3)

            save_path  = str(workspace / f"image_{i:02d}.jpg")
            seed       = _SEEDS[i % len(_SEEDS)]
            core_query = query.split(",")[0].strip()

            logger.info(f"\n🖼  Image {i+1}/{len(queries)}: {query[:70]}...")

            url     = self._build_url(query, seed=seed)
            success = self._download(url, save_path, attempt_label=f"[scene {i+1}]")

            if not success:
                logger.warning(f"  ↩ Fallback 1: simplified prompt '{core_query}'")
                success = self._download(
                    self._build_url(core_query, seed=seed + 1), save_path, "[fallback-1]"
                )

            if not success:
                logger.warning("  ↩ Fallback 2: random seed")
                success = self._download(
                    self._build_url(core_query, seed=random.randint(1, 99999)), save_path, "[fallback-2]"
                )

            if success:
                image_paths.append(save_path)
            else:
                logger.error(f"  ⚠ Image {i+1} failed all attempts — skipping.")

        return image_paths
