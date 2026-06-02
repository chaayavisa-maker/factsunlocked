"""
VideoAgent – assembles scenes (image + audio) into a vertical MP4.
Works for both channels; pass channel config to customise watermark/font.
"""

from pathlib import Path
from src.utils.logger import get_logger
import os

logger = get_logger(__name__)


def build_video(
    scenes: list,
    image_paths: list,
    audio_paths: list,
    output_path: Path,
    resolution: tuple = (1080, 1920),
    fps: int = 30,
    font_size: int = 72,
    watermark: str = None,
    hook_text: str = None,
) -> Path:
    """
    Build final video from per-scene images + audio.

    Parameters
    ----------
    scenes       : list of scene dicts (with 'narration' key for subtitles)
    image_paths  : list of Path objects for scene images
    audio_paths  : list of Path objects for scene audio
    output_path  : where to save the final MP4
    watermark    : optional bottom-right text overlay (e.g. "AstroFacts ✨")
    hook_text    : optional opening text overlay (first 2s)
    """
    font = os.environ.get("MOVIEPY_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

    try:
        from moviepy import (
            ImageClip,
            AudioFileClip,
            TextClip,
            CompositeVideoClip,
            concatenate_videoclips,
        )
    except ImportError:
        raise ImportError("moviepy is not installed. Run: pip install moviepy")

    clips = []
    w, h = resolution

    for i, (scene, img_path, aud_path) in enumerate(
        zip(scenes, image_paths, audio_paths)
    ):
        audio = AudioFileClip(str(aud_path))
        duration = audio.duration

        img_clip = (
            ImageClip(str(img_path))
            .with_duration(duration)        # v1: .set_duration()
            .resized(resolution)            # v1: .resize()
        )

        layers = [img_clip]

        # Subtitle / narration overlay
        narration = scene.get("narration", "")
        if narration:
            txt = (
                TextClip(
                    text=narration,         # v1: positional arg
                    font_size=font_size,    # v1: fontsize=
                    color="white",
                    stroke_color="black",
                    stroke_width=2,
                    method="caption",
                    size=(w - 80, None),
                    font=font,
                )
                .with_position(("center", h * 0.75))   # v1: .set_position()
                .with_duration(duration)                # v1: .set_duration()
            )
            layers.append(txt)

        # Watermark
        if watermark:
            wm = (
                TextClip(
                    text=watermark,
                    font_size=36,           # v1: fontsize=
                    color="white",
                    stroke_color="black",
                    stroke_width=1,
                    font="Arial",
                )
                .with_position((w - 250, h - 80))   # v1: .set_position()
                .with_duration(duration)             # v1: .set_duration()
            )
            layers.append(wm)

        # Hook text on first scene only
        if i == 0 and hook_text:
            hook = (
                TextClip(
                    text=hook_text,
                    font_size=int(font_size * 0.8),  # v1: fontsize=
                    color="yellow",
                    stroke_color="black",
                    stroke_width=2,
                    method="caption",
                    size=(w - 80, None),
                    font=font,
                )
                .with_position(("center", h * 0.1))        # v1: .set_position()
                .with_duration(min(3, duration))            # v1: .set_duration()
            )
            layers.append(hook)

        scene_clip = CompositeVideoClip(layers).with_audio(audio)  # v1: .set_audio()
        clips.append(scene_clip)

    logger.info(f"Concatenating {len(clips)} scenes…")
    final = concatenate_videoclips(clips, method="compose")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Rendering video to {output_path}")
    final.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        threads=2,
        logger=None,
    )
    logger.info("Video render complete.")
    return output_path
