import asyncio
import aiofiles
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Best voices for engaging short-form content
VOICE_OPTIONS = [
    "en-US-AriaNeural",      # warm, natural female — primary
    "en-US-GuyNeural",       # confident male — alternative
    "en-US-JennyNeural",     # friendly female
    "en-GB-SoniaNeural",     # British female — sounds authoritative
]


class NarrationAgent:
    def __init__(self, voice: str = "en-US-AriaNeural", rate: str = "+5%"):
        self.voice = voice
        self.rate = rate  # slight speed-up keeps Shorts punchy

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _generate_clip(self, text: str, output_path: Path) -> Path:
        """Generate a single TTS audio clip via edge-tts."""
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            volume="+0%",
        )
        await communicate.save(str(output_path))

        if not output_path.exists() or output_path.stat().st_size < 1000:
            raise RuntimeError(f"TTS output missing or empty: {output_path}")

        logger.info(f"  ✓ Audio clip: {output_path.name}")
        return output_path

    async def generate_all_narration(
        self, script: dict, workspace: Path
    ) -> list[Path]:
        """
        Generates one MP3 per scene, plus an outro clip.
        Returns ordered list of audio paths matching scenes.
        """
        audio_dir = workspace / "audio"
        audio_dir.mkdir(exist_ok=True)

        paths = []
        for scene in script["scenes"]:
            n = scene["scene_number"]
            out = audio_dir / f"scene_{n:02d}.mp3"
            text = scene["narration"].strip()
            await self._generate_clip(text, out)
            paths.append(out)

        # Outro clip
        outro_text = script.get("outro", "Subscribe for more mind-blowing facts every day!")
        outro_path = audio_dir / "outro.mp3"
        await self._generate_clip(outro_text, outro_path)
        paths.append(outro_path)

        logger.info(f"All {len(paths)} audio clips generated.")
        return paths

    async def get_audio_duration(self, audio_path: Path) -> float:
        """Returns duration in seconds using moviepy."""
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(str(audio_path))
        duration = clip.duration
        clip.close()
        return duration
