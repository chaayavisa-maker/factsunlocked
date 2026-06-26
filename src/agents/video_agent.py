import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Shared encoder settings — every intermediate clip must use these so that
# the final concat step can stream-copy without re-encoding.
_ENCODE_FLAGS = ["-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p"]

# Minimum scene duration guard — never show an image for less than 2 seconds
_MIN_SCENE_DURATION = 2.0

# Caption position — bottom-third (Shorts standard)
_CAPTION_Y = "(h*0.72)"


class VideoAgent:
    def __init__(self, settings: dict):
        self.w = 1080
        self.h = 1920
        self.fps = settings["video"].get("fps", 30)
        self.font_size = settings["video"].get("font_size", 68)
        self.music_volume = settings["video"].get("music_volume", 0.12)
        self.watermark = settings["video"].get("watermark", None)

    # ------------------------------------------------------------------
    # Ken Burns effect via ffmpeg zoompan (fast, no per-frame Python)
    # ------------------------------------------------------------------
    def _ken_burns(self, img_path: str, out_path: str, duration: float, zoom_in: bool = True):
        duration = max(duration, _MIN_SCENE_DURATION)
        frames = int(duration * self.fps)

        if zoom_in:
            zoom_expr = "min(zoom+0.0004,1.12)"
        else:
            zoom_expr = "if(eq(on,1),1.12,max(zoom-0.0004,1.0))"

        vf = (
            f"scale={self.w*2}:{self.h*2},"
            f"zoompan="
            f"z='{zoom_expr}':"
            f"d={frames}:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={self.w}x{self.h},"
            f"fps={self.fps},"
            f"setpts=PTS-STARTPTS"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", img_path,
            "-vf", vf,
            "-t", str(duration),
            *_ENCODE_FLAGS,
            out_path
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Ken Burns failed:\n{result.stderr.decode()}")

    # ------------------------------------------------------------------
    # Caption overlay — bottom-third, word-wrapped, drop-shadow style
    # ------------------------------------------------------------------
    def _wrap_text(self, text: str, max_chars: int = 26) -> str:
        return "\n".join(textwrap.wrap(text, width=max_chars))

    def _add_caption(self, video_path: str, text: str, out_path: str,
                     watermark: str = None, hook_text: str = None):
        if not text.strip():
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, *_ENCODE_FLAGS, out_path],
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Caption passthrough failed:\n{result.stderr.decode()}"
                )
            return

        wrapped = self._wrap_text(text, max_chars=26)
        tmpfiles = []

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as tf:
                tf.write(wrapped)
                txt_path = tf.name
                tmpfiles.append(txt_path)

            font_size = self.font_size

            shadow = (
                f"drawtext="
                f"textfile='{txt_path}':"
                f"fontsize={font_size}:"
                f"fontcolor=black@0.85:"
                f"font=DejaVu-Sans-Bold:"
                f"x=(w-text_w)/2+3:"
                f"y={_CAPTION_Y}+3:"
                f"line_spacing=12:"
                f"fix_bounds=true"
            )
            main = (
                f"drawtext="
                f"textfile='{txt_path}':"
                f"fontsize={font_size}:"
                f"fontcolor=white:"
                f"font=DejaVu-Sans-Bold:"
                f"bordercolor=black:"
                f"borderw=2:"
                f"box=1:"
                f"boxcolor=black@0.45:"
                f"boxborderw=20:"
                f"x=(w-text_w)/2:"
                f"y={_CAPTION_Y}:"
                f"line_spacing=12:"
                f"fix_bounds=true"
            )

            filters = [shadow, main]

            if watermark:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as wf:
                    wf.write(watermark)
                    wm_path = wf.name
                    tmpfiles.append(wm_path)
                filters.append(
                    f"drawtext="
                    f"textfile='{wm_path}':"
                    f"fontsize=32:"
                    f"fontcolor=white@0.75:"
                    f"font=DejaVu-Sans-Bold:"
                    f"x=w-text_w-30:"
                    f"y=h-text_h-40:"
                    f"fix_bounds=true"
                )

            if hook_text:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as hf:
                    hf.write(self._wrap_text(hook_text, max_chars=22))
                    hook_path = hf.name
                    tmpfiles.append(hook_path)
                filters.append(
                    f"drawtext="
                    f"textfile='{hook_path}':"
                    f"fontsize={int(font_size*0.75)}:"
                    f"fontcolor=yellow:"
                    f"font=DejaVu-Sans-Bold:"
                    f"bordercolor=black:"
                    f"borderw=2:"
                    f"x=(w-text_w)/2:"
                    f"y=(h*0.08):"
                    f"line_spacing=10:"
                    f"fix_bounds=true"
                )

            vf = ",".join(filters)
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", vf,
                *_ENCODE_FLAGS,
                out_path,
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(f"Caption failed:\n{result.stderr.decode()}")
        finally:
            for f in tmpfiles:
                try:
                    os.unlink(f)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helper: probe duration of any media file
    # ------------------------------------------------------------------
    @staticmethod
    def _probe_duration(path: str) -> float:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True, text=True, check=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Pad video so its duration matches target_duration (freeze last frame)
    # ------------------------------------------------------------------
    def _pad_video_to_duration(self, video_path: str, out_path: str, target_duration: float):
        """
        Extend video to target_duration by freezing the last frame.
        If video is already >= target_duration, stream-copy to out_path unchanged.
        """
        video_dur = self._probe_duration(video_path)
        pad_seconds = target_duration - video_dur

        if pad_seconds <= 0.05:
            # Already long enough — just copy
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-c", "copy", out_path],
                capture_output=True, check=True,
            )
            return

        logger.info(f"  Padding video by {pad_seconds:.2f}s to cover outro narration")
        # tpad=stop_mode=clone freezes the last frame for stop_duration seconds
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}",
            *_ENCODE_FLAGS,
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Video padding failed:\n{result.stderr.decode()}")

    # ------------------------------------------------------------------
    # Main assembly
    # ------------------------------------------------------------------
    def assemble(
        self,
        workspace: str,
        image_paths: list,
        narration_path: str,
        music_path: str | None,
        script: dict,
        scene_durations: list[float] | None = None,
        hook_text: str | None = None,
    ) -> str:
        ws = Path(workspace)

        scene_texts = (
            [script.get("hook", "")]
            + [
                (s.get("narration", "") if isinstance(s, dict) else str(s))
                for s in script.get("scenes", [])
            ]
            + [script.get("payoff", "")]
        )

        n = len(image_paths)
        scene_texts = scene_texts[:n]
        while len(scene_texts) < n:
            scene_texts.append("")

        # ── Scene durations ──────────────────────────────────────────────
        if scene_durations and len(scene_durations) >= n:
            durations = [max(d, _MIN_SCENE_DURATION) for d in scene_durations[:n]]
            logger.info(f"Using per-scene durations: {[f'{d:.1f}s' for d in durations]}")
        else:
            try:
                total_duration = self._probe_duration(narration_path)
            except Exception:
                total_duration = n * 10.0
            even = max(total_duration / n, _MIN_SCENE_DURATION)
            durations = [even] * n
            logger.info(f"Even split: {even:.1f}s × {n} scenes")

        # 1. Ken Burns + caption for each scene
        scene_paths = []
        for i, (img_path, text, dur) in enumerate(zip(image_paths, scene_texts, durations)):
            zoom_in = (i % 2 == 0)
            kb_path = str(ws / f"kb_{i:02d}.mp4")
            cap_path = str(ws / f"scene_{i:02d}.mp4")

            logger.info(f"\n🎬 Scene {i+1}/{n} ({dur:.1f}s): Ken Burns...")
            self._ken_burns(img_path, kb_path, dur, zoom_in)

            logger.info(f"🎬 Scene {i+1}/{n}: Caption '{text[:40]}...'")
            scene_hook = hook_text if (i == 0 and hook_text) else None
            self._add_caption(
                kb_path, text, cap_path,
                watermark=self.watermark,
                hook_text=scene_hook,
            )
            scene_paths.append(cap_path)

        # 2. Concatenate scenes
        concat_list = str(ws / "concat.txt")
        with open(concat_list, "w") as f:
            for p in scene_paths:
                f.write(f"file '{Path(p).resolve()}'\n")

        raw_video = str(ws / "video_silent.mp4")
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            raw_video
        ], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Concat failed:\n{result.stderr.decode()}")

        # 3. Mix narration + optional background music
        # scene_durations already includes outro time (absorbed by narration_agent),
        # so raw_video duration matches narration_path — no padding needed.
        final_path = str(ws / "final_video.mp4")

        if music_path and os.path.exists(music_path):
            # duration=first → audio ends when narration ends (not when music loops end)
            # Music fades out over the last 2 seconds of narration
            audio_filter = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={self.music_volume},"
                f"afade=t=in:st=0:d=1,"
                f"aloop=loop=-1:size=2000000000[music];"
                f"[narr][music]amix=inputs=2:duration=first:dropout_transition=2[out]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_video,
                "-i", narration_path,
                "-i", music_path,
                "-filter_complex", audio_filter,
                "-map", "0:v",
                "-map", "[out]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                final_path
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", raw_video,
                "-i", narration_path,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                final_path
            ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Final mix failed:\n{result.stderr.decode()}")

        logger.info(f"\n✅ Final video: {final_path}")
        return final_path
