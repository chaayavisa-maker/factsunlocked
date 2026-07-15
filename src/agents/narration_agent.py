import asyncio
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential
from src.utils.logger import get_logger
import subprocess
import tempfile

logger = get_logger(__name__)

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

    def _concat_audio_ffmpeg(self, audio_paths: list[Path], output_path: Path) -> bool:
        """
        Concatenate audio files using ffmpeg (not moviepy).
        This is more reliable and doesn't depend on moviepy internals.
        
        Returns True if successful, False otherwise.
        """
        if not audio_paths:
            return False

        try:
            # Create a temporary concat file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                for path in audio_paths:
                    f.write(f"file '{Path(path).resolve()}'\n")
                concat_file = f.name

            logger.info(f"Concatenating {len(audio_paths)} audio clips via ffmpeg...")

            # Use ffmpeg concat demuxer
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            # Clean up temp file
            try:
                Path(concat_file).unlink()
            except Exception:
                pass

            if result.returncode == 0:
                logger.info(f"✅ Audio concatenation successful → {output_path}")
                return True
            else:
                logger.warning(f"ffmpeg concat failed: {result.stderr[:200]}")
                return False

        except Exception as e:
            logger.warning(f"ffmpeg concatenation error: {e}")
            return False

    def _concat_audio_moviepy(self, audio_paths: list[Path], output_path: Path) -> bool:
        """
        Concatenate audio using moviepy (faster if it works).
        Falls back gracefully if moviepy fails.
        
        Returns True if successful, False otherwise.
        """
        try:
            from moviepy.editor import AudioFileClip, concatenate_audioclips

            audio_clips = [AudioFileClip(str(p)) for p in audio_paths]
            combined = concatenate_audioclips(audio_clips)
            combined.write_audiofile(str(output_path), verbose=False, logger=None)

            for c in audio_clips:
                c.close()
            combined.close()

            logger.info(f"✅ Audio concatenation successful (moviepy) → {output_path}")
            return True

        except Exception as e:
            logger.warning(f"moviepy concatenation failed ({type(e).__name__}: {str(e)[:100]})")
            return False

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

        # The last clip is the outro — it's included in audio but excluded
        # from scene_durations (no matching image for it).
        outro_duration = durations[-1]
        scene_durations = durations[:-1]
        scene_clips = clips[:-1]
        outro_clip = clips[-1]

        # Absorb outro duration into the last scene so the last image keeps
        # playing during the outro instead of freezing on a padded frame.
        if scene_durations:
            scene_durations[-1] += outro_duration
            logger.info(
                f"  Absorbed {outro_duration:.2f}s outro into last scene "
                f"(last scene now {scene_durations[-1]:.2f}s)"
            )

        # Concatenate all clips (including outro) into narration.mp3
        combined_path = workspace / "narration.mp3"

        # Try concatenation in priority order:
        # 1. ffmpeg concat (most reliable)
        # 2. moviepy (faster if available)
        # 3. Fail with proper error

        success = self._concat_audio_ffmpeg(clips, combined_path)

        if not success:
            logger.info("Falling back to moviepy concatenation...")
            success = self._concat_audio_moviepy(clips, combined_path)

        if success:
            logger.info(f"Narration combined → {combined_path} ({sum(durations):.1f}s total)")
            return combined_path, scene_durations
        else:
            raise RuntimeError(
                "❌ Audio concatenation failed (both ffmpeg and moviepy).\n"
                "This should not happen — please check ffmpeg installation."
            )

    async def generate_all_narration(self, script: dict, workspace: Path) -> list[Path]:
        """
        Generates one MP3 per segment in order:
          hook → scenes[0..n] → payoff → outro
        Returns ordered list of audio paths.
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
        outro = script.get("outro", "Subscribe for a new fact every day!")
        segments.append(("outro", outro))

        # ── Generate clips ────────────────────────────────────────────────
        paths: list[Path] = []
        for label, text in segments:
            out = audio_dir / f"{label}.mp3"
            await self._generate_clip(text, out)
            paths.append(out)

        logger.info(f"Generated {len(paths)} audio clips: {[p.name for p in paths]}")
        return paths
