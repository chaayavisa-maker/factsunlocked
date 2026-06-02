"""
NarrationAgent – converts text to speech using edge-tts (free, no key).
"""

import asyncio
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def _synthesise(text: str, voice: str, output_path: Path) -> None:
    import edge_tts
    tts = edge_tts.Communicate(text, voice)
    await tts.save(str(output_path))


def generate_narration(
    text: str,
    output_path: Path,
    voice: str = "en-US-AriaNeural",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Generating narration ({voice}): {text[:60]}…")
    asyncio.run(_synthesise(text, voice, output_path))
    logger.info(f"Audio saved to {output_path}")
    return output_path


def generate_scene_narrations(
    scenes: list,
    workspace: Path,
    voice: str = "en-US-AriaNeural",
) -> list:
    """
    Generate one audio file per scene.
    Scenes must have a 'narration' key.
    Returns list of Paths.
    """
    paths = []
    for i, scene in enumerate(scenes):
        text = scene.get("narration", "")
        out = workspace / f"narration_{i:02d}.mp3"
        path = generate_narration(text, out, voice=voice)
        paths.append(path)
    return paths
