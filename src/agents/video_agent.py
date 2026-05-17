import os
import subprocess
import textwrap
from pathlib import Path


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
        frames = int(duration * self.fps)

        if zoom_in:
            zoom_expr = "min(zoom+0.0005,1.15)"
        else:
            zoom_expr = "if(eq(on,1),1.15,max(zoom-0.0005,1.0))"

        vf = (
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
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            out_path
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"Ken Burns failed:\n{result.stderr.decode()}")

    # ------------------------------------------------------------------
    # Caption overlay via ffmpeg drawtext
    # ------------------------------------------------------------------
    def _wrap_text(self, text: str, max_chars: int = 22) -> str:
        return "\n".join(textwrap.wrap(text, width=max_chars))

    def _escape_drawtext(self, text: str) -> str:
        wrapped = self._wrap_text(text, max_chars=22)
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
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-c", "copy", out_path],
                check=True, capture_output=True
            )
            return

        escaped = self._escape_drawtext(text)

        vf = (
            f"drawtext="
            f"text='{escaped}':"
            f"fontsize={self.font_size}:"
            f"fontcolor=white:"
            f"font='DejaVu-Sans-Bold':"
            f"bordercolor=black:"
            f"borderw=3:"
            f"box=1:"
            f"boxcolor=black@0.55:"
            f"boxborderw=18:"
            f"x=(w-text_w)/2:"
            f"y=(h-text_h)/2:"
            f"line_spacing=10:"
            f"fix_bounds=true"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:a", "copy",
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
    ) -> str:
        ws = Path(workspace)

        scene_texts = (
            [script.get("hook", "")]
            + script.get("scenes", [])
            + [script.get("payoff", "")]
        )

        n = len(image_paths)
        scene_texts = scene_texts[:n]
        while len(scene_texts) < n:
            scene_texts.append("")

        # Get narration duration to split evenly across scenes
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    narration_path
                ],
                capture_output=True, text=True, check=True
            )
            total_duration = float(result.stdout.strip())
        except Exception:
            total_duration = n * 10.0

        scene_duration = total_duration / n

        # 1. Ken Burns + caption for each scene
        scene_paths = []
        for i, (img_path, text) in enumerate(zip(image_paths, scene_texts)):
            zoom_in = (i % 2 == 0)
            kb_path = str(ws / f"kb_{i:02d}.mp4")
            cap_path = str(ws / f"scene_{i:02d}.mp4")

            print(f"Scene {i+1}/{n}: Ken Burns...")
            self._ken_burns(img_path, kb_path, scene_duration, zoom_in)

            print(f"Scene {i+1}/{n}: Caption...")
            self._add_caption(kb_path, text, cap_path)
            scene_paths.append(cap_path)

        # 2. Concatenate scenes
        concat_list = str(ws / "concat.txt")
        with open(concat_list, "w") as f:
            for p in scene_paths:
                f.write(f"file '{p}'\n")

        raw_video = str(ws / "video_silent.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            raw_video
        ], check=True, capture_output=True)

        # 3. Mix narration + optional background music
        final_path = str(ws / "final_video.mp4")

        if music_path and os.path.exists(music_path):
            audio_filter = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={self.music_volume},"
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

        print(f"Final video: {final_path}")
        return final_path
