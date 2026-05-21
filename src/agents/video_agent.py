import os
import subprocess
import textwrap
from pathlib import Path

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
            f"scale={self.w*2}:{self.h*2},"   # upscale first → cleaner zoompan
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

    def _escape_drawtext(self, text: str) -> str:
        wrapped = self._wrap_text(text, max_chars=26)
        lines = wrapped.split("\n")
        escaped = []
        for line in lines:
            line = line.replace("\\", "\\\\")
            line = line.replace("'", "\\'")
            line = line.replace(":", "\\:")
            escaped.append(line)
        return "\\n".join(escaped)

    def _add_caption(self, video_path: str, text: str, out_path: str):
        if not text.strip():
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, *_ENCODE_FLAGS, out_path],
                capture_output=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Caption passthrough failed:\n{result.stderr.decode()}")
            return

        escaped = self._escape_drawtext(text)
        font_size = self.font_size

        # Two drawtext layers: shadow offset + main text (simulates drop shadow)
        shadow = (
            f"drawtext="
            f"text='{escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor=black@0.85:"
            f"font='DejaVu-Sans-Bold':"
            f"x=(w-text_w)/2+3:"
            f"y={_CAPTION_Y}+3:"
            f"line_spacing=12:"
            f"fix_bounds=true"
        )
        main = (
            f"drawtext="
            f"text='{escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"font='DejaVu-Sans-Bold':"
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

        vf = f"{shadow},{main}"

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            *_ENCODE_FLAGS,
            out_path
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Caption failed:\n{result.stderr.decode()}")

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
    ) -> str:
        ws = Path(workspace)

        # Build scene text list: hook → body scenes → payoff
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
            # Use per-clip durations from narration agent (accurate)
            durations = [max(d, _MIN_SCENE_DURATION) for d in scene_durations[:n]]
            print(f"Using per-scene durations: {[f'{d:.1f}s' for d in durations]}")
        else:
            # Fallback: measure total narration and split evenly
            try:
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        narration_path,
                    ],
                    capture_output=True, text=True, check=True,
                )
                total_duration = float(result.stdout.strip())
            except Exception:
                total_duration = n * 10.0
            even = max(total_duration / n, _MIN_SCENE_DURATION)
            durations = [even] * n
            print(f"Even split: {even:.1f}s × {n} scenes")

        # 1. Ken Burns + caption for each scene
        scene_paths = []
        for i, (img_path, text, dur) in enumerate(zip(image_paths, scene_texts, durations)):
            zoom_in = (i % 2 == 0)
            kb_path = str(ws / f"kb_{i:02d}.mp4")
            cap_path = str(ws / f"scene_{i:02d}.mp4")

            print(f"\n🎬 Scene {i+1}/{n} ({dur:.1f}s): Ken Burns...")
            self._ken_burns(img_path, kb_path, dur, zoom_in)

            print(f"🎬 Scene {i+1}/{n}: Caption '{text[:40]}...'")
            self._add_caption(kb_path, text, cap_path)
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
        final_path = str(ws / "final_video.mp4")

        if music_path and os.path.exists(music_path):
            # Fade music in over first 1s, out over last 2s for polish
            audio_filter = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={self.music_volume},"
                f"afade=t=in:st=0:d=1,"
                f"aloop=loop=-1:size=2e+09[music];"
                f"[narr][music]amix=inputs=2:duration=first[out]"
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
                "-shortest",
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
                "-shortest",
                final_path
            ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Final mix failed:\n{result.stderr.decode()}")

        print(f"\n✅ Final video: {final_path}")
        return final_path
