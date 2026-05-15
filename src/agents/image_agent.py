import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from urllib.parse import quote
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import setup_logger

logger = setup_logger(__name__)

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

# Style suffix appended to every prompt for consistent quality
STYLE_SUFFIX = (
    ", cinematic, photorealistic, high detail, 4k, dramatic lighting, "
    "sharp focus, professional photography, no text, no watermark"
)
NEGATIVE_CONCEPTS = "blurry, low quality, text, watermark, nsfw, cartoon, drawing"


class ImageAgent:
    def __init__(self, width: int = 1080, height: int = 1920):
        self.width = width
        self.height = height

    def _build_url(self, prompt: str, seed: int) -> str:
        enhanced = prompt + STYLE_SUFFIX
        encoded = quote(enhanced)
        return (
            f"{POLLINATIONS_URL.format(prompt=encoded)}"
            f"?width={self.width}&height={self.height}"
            f"&seed={seed}&nologo=true&enhance=true"
        )

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=3, max=20))
    async def _download_image(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        output_path: Path,
        seed: int,
    ) -> Path:
        url = self._build_url(prompt, seed)
        logger.info(f"  Generating image for scene (seed={seed})...")

        async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
            resp.raise_for_status()
            content = await resp.read()

        if len(content) < 5000:
            raise ValueError(f"Image too small ({len(content)} bytes) — likely an error page")

        async with aiofiles.open(output_path, "wb") as f:
            await f.write(content)

        logger.info(f"  ✓ Image saved: {output_path.name} ({len(content)//1024}KB)")
        return output_path

    async def generate_all_images(
        self, script: dict, workspace: Path
    ) -> list[Path]:
        """
        Generates one image per scene concurrently.
        Returns ordered list of image paths.
        """
        images_dir = workspace / "images"
        images_dir.mkdir(exist_ok=True)

        scenes = script["scenes"]
        tasks = []

        connector = aiohttp.TCPConnector(limit=3)  # polite concurrency
        async with aiohttp.ClientSession(connector=connector) as session:
            for scene in scenes:
                n = scene["scene_number"]
                out = images_dir / f"scene_{n:02d}.jpg"
                prompt = scene["image_prompt"]
                seed = 1000 + n * 37  # deterministic but varied seeds
                tasks.append(self._download_image(session, prompt, out, seed))

            # Stagger requests slightly to avoid hammering the API
            results = []
            for i, task in enumerate(tasks):
                if i > 0:
                    await asyncio.sleep(1.5)
                result = await task
                results.append(result)

        logger.info(f"All {len(results)} images generated.")
        return results
