import asyncio
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import setup_logger

logger = setup_logger(__name__)

VOICE_OPTIONS = [
    "en-US-AriaNeural",      # warm, natural female — primary
    "en-US-GuyNeural",       # confident male — alternative
    "en-US-JennyNeural",     # friendly female
    "en-GB-SoniaNeural",     # British female — sounds authoritative
]


class NarrationAgent:
    def __init__(self, settings: dict = None, voice: str = "en-US-AriaNeural", rate: str = "+5%"):
        if settings is not None:
            tts_cfg = settings.get("tts", {})
            self.voice = tts_cfg.get("voice", voice)
            self.rate = tts_cfg.get("rate", rate)
        else:
            self.voice = voice
            self.rate = rate

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

        if not output_path.exists() or output_path.stat().st_size < 500:
            raise RuntimeError(f"TTS output missing or empty: {output_path}")

        logger.info(f"  ✓ Audio clip: {output_path.name}")
        return output_path

    def _get_clip_duration(self, path: Path) -> float:
        """Return duration of an audio clip in seconds using ffprobe."""
        import subprocess
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True, text=True, check=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    async def generate_all_narration(self, script: dict, workspace: Path) -> list[Path]:
        """
        Generates one MP3 per segment in order:
          hook → scenes[0..n] → payoff → outro
        Returns ordered list of audio paths with their durations.
        """
        audio_dir = workspace / "audio"
        audio_dir.mkdir(exist_ok=True)

        # ── Build ordered segment list ────────────────────────────────────
        segments: list[tuple[str, str]] = []  # (label, text)

        # Hook
        hook = script.get("hook", "").strip()
        if hook:
            segments.append(("hook", hook))

        # Body scenes
        for i, scene in enumerate(script.get("scenes", [])):
            if isinstance(scene, dict):
                text = scene.get("narration", "").strip()
            else:
                text = str(scene).strip()
            if text:
                segments.append((f"scene_{i+1:02d}", text))

        # Payoff
        payoff = script.get("payoff", "").strip()
        if payoff:
            segments.append(("payoff", payoff))

        # Outro CTA
        outro = script.get("outro", "Subscribe for more mind-blowing space facts every day!")
        segments.append(("outro", outro))

        # ── Generate clips ────────────────────────────────────────────────
        paths: list[Path] = []
        for label, text in segments:
            out = audio_dir / f"{label}.mp3"
            await self._generate_clip(text, out)
            paths.append(out)

        logger.info(f"Generated {len(paths)} audio clips: {[p.name for p in paths]}")
        return paths

    async def generate(self, script: dict, workspace: Path) -> tuple[Path, list[float]]:
        """
        Public method called by main.py.
        Returns (combined_narration_path, per_scene_durations).

        per_scene_durations maps to the image_paths list:
          [hook_duration, scene1_duration, ..., payoff_duration]
        The outro is audio-only and NOT counted in scene durations.
        """
        clips = await self.generate_all_narration(script, workspace)

        if not clips:
            raise RuntimeError("NarrationAgent: no audio clips were generated.")

        # Measure per-clip durations BEFORE concat so video can time each scene
        durations = [self._get_clip_duration(p) for p in clips]

        # The last clip is the outro — it's included in audio but the last
        # image (payoff) should already have its own clip before it.
        # scene_durations = all clips except outro
        scene_durations = durations[:-1]  # exclude outro
        outro_clip = clips[-1]
        scene_clips = clips[:-1]

        # Concatenate all clips (including outro) into narration.mp3
        combined_path = workspace / "narration.mp3"
        try:
            from moviepy.editor import AudioFileClip, concatenate_audioclips

            audio_clips = [AudioFileClip(str(p)) for p in clips]
            combined = concatenate_audioclips(audio_clips)
            combined.write_audiofile(str(combined_path), verbose=False, logger=None)

            for c in audio_clips:
                c.close()
            combined.close()

            logger.info(f"Narration combined → {combined_path} ({sum(durations):.1f}s total)")
        except Exception as e:
            logger.warning(f"Concatenation failed ({e}), falling back to first clip.")
            return clips[0], scene_durations

        return combined_path, scene_durations

    async def get_audio_duration(self, audio_path: Path) -> float:
        """Returns duration in seconds using moviepy."""
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(str(audio_path))
        duration = clip.duration
        clip.close()
        return duration
