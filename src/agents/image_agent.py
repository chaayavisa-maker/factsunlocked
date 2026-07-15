import os
import time
import random
import requests
from pathlib import Path
from urllib.parse import quote
from src.utils.logger import get_logger

logger = get_logger(__name__)

_NEGATIVE = (
    # ── Language / script artefacts ──────────────────────────────────────
    "chinese characters, chinese text, chinese writing, hanzi, kanji, "
    "japanese text, korean text, asian script, cyrillic, arabic script, "
    "non-latin characters, foreign language text, "
    # ── Generic text / branding ───────────────────────────────────────────
    "text, watermark, logo, caption, subtitle, words, letters, "
    # ── Quality ───────────────────────────────────────────────────────────
    "blurry, low quality, ugly, deformed, cartoon, anime, drawing, painting, "
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
            "western style, no text, no writing, latin alphabet only, "
            "8K resolution, professional photography, award winning"
        )
        url = (
            # FIX: pin to `flux` model — far less likely to hallucinate CJK text
            f"https://gen.pollinations.ai/image/{quote(full_prompt)}"
            f"?model=flux"
            f"&width={self.width}&height={self.height}"
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

    def _download(self, url: str, save_path: str, attempt_label: str = "", allow_token: bool = True) -> bool:
        # NOTE: Pollinations retired the passive hourly Pollen drip in 2026 — a 402
        # "insufficient balance" no longer refills itself if you just wait, so we no
        # longer sleep for an hour hoping it will. Instead, on a balance error we drop
        # the paid add-ons (token / enhance / nologo) for the rest of THIS image and
        # retry on the plain Flux endpoint, which Pollinations documents as free and
        # unlimited regardless of Pollen balance. See:
        # https://github.com/pollinations/pollinations/blob/master/enter.pollinations.ai/POLLEN_FAQ.md
        dropped_token = not allow_token

        for attempt in range(self.max_retries):
            try:
                req_url = url if allow_token else self._strip_paid_params(url)
                resp = requests.get(req_url, headers=_HEADERS, timeout=self.timeout, stream=True)
                if resp.status_code == 200 and len(resp.content) > 10_000:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    tag = attempt_label + (" [free tier]" if dropped_token else "")
                    logger.info(f"  ✓ Image saved ({len(resp.content)//1024}KB) {tag}")
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

                    if allow_token and ("Insufficient balance" in msg or "balance" in msg.lower()):
                        logger.warning(
                            "  💰 Insufficient Pollen balance — dropping token/enhance and "
                            "retrying on the free, unlimited anonymous Flux endpoint."
                        )
                        allow_token = False
                        dropped_token = True
                        continue  # retry immediately on the free path, no sleep needed

                    # queue full or other 402 — short exponential backoff
                    self._backoff(attempt, base=15)
                elif resp.status_code == 429:
                    # Anonymous/free tier is rate-limited (documented as roughly one
                    # request per ~15s), not balance-limited — a short wait clears it.
                    logger.warning("  🚦 Rate limited — waiting for the anonymous-tier window to clear.")
                    time.sleep(20)
                else:
                    self._backoff(attempt, base=5)

            except Exception as e:
                logger.warning(f"  ✗ Download attempt {attempt+1} failed: {e}")
                self._backoff(attempt)
        return False

    @staticmethod
    def _strip_paid_params(url: str) -> str:
        """Remove key/enhance/nologo (Pollen-costing add-ons) to fall back to the
        free anonymous Flux endpoint, which Pollinations documents as unlimited."""
        for param in ("&nologo=true", "&enhance=true"):
            url = url.replace(param, "")
        import re
        url = re.sub(r"&key=[^&]*", "", url)
        return url

    def generate_all(self, script: dict, workspace: Path) -> list:
        queries = script.get("image_queries", [])
        image_paths = []

        for i, query in enumerate(queries):
            if i > 0:
                # Pollinations' documented anonymous-tier cadence is roughly one
                # request per ~15s; pacing to it up front avoids most 429s rather
                # than just reacting to them after the fact.
                time.sleep(15 if not self._token else 5)

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
