import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    TextClip,
    ColorClip,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Video spec — YouTube Shorts portrait format
WIDTH, HEIGHT = 1080, 1920
FPS = 24

# Branding colours
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (255, 200, 50)      # gold accent for facts
SHADOW_COLOR = (0, 0, 0, 180)
BAR_COLOR = (0, 0, 0, 160)         # semi-transparent text bar


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a decent system font, fall back to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _render_frame(
    image_path: Path,
    on_screen_text: str,
    scene_number: int,
    total_scenes: int,
) -> np.ndarray:
    """
    Renders a single video frame:
    - Full-bleed background image (cropped to 1080×1920)
    - Gradient overlay for readability
    - On-screen text bar at the bottom third
    - Progress indicator dots at the top
    Returns an RGBA numpy array.
    """
    # --- Background ---
    bg = Image.open(image_path).convert("RGBA")
    bg = _crop_center(bg, WIDTH, HEIGHT)

    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    canvas.paste(bg, (0, 0))

    draw = ImageDraw.Draw(canvas)

    # --- Gradient overlay (bottom 40% for text legibility) ---
    grad_h = int(HEIGHT * 0.45)
    grad_y_start = HEIGHT - grad_h
    for y in range(grad_h):
        alpha = int(200 * (y / grad_h) ** 1.5)
        draw.rectangle(
            [(0, grad_y_start + y), (WIDTH, grad_y_start + y + 1)],
            fill=(0, 0, 0, alpha),
        )

    # --- On-screen text ---
    font_large = _load_font(72)
    font_small = _load_font(42)

    text_upper = on_screen_text.upper()
    margin = 60
    max_text_w = WIDTH - margin * 2

    lines = _wrap_text(text_upper, font_large, max_text_w)
    line_h = 80
    total_text_h = len(lines) * line_h
    text_y_start = HEIGHT - 320 - total_text_h

    for i, line in enumerate(lines):
        y = text_y_start + i * line_h
        bbox = font_large.getbbox(line)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2

        # Shadow
        for dx, dy in [(-3, 3), (3, 3), (-3, -3), (3, -3)]:
            draw.text((x + dx, y + dy), line, font=font_large, fill=(0, 0, 0, 200))
        # Accent colour text
        draw.text((x, y), line, font=font_large, fill=ACCENT_COLOR)

    # --- Progress dots ---
    dot_r = 10
    dot_spacing = 30
    total_dots_w = total_scenes * dot_spacing - dot_spacing + dot_r * 2
    dot_x_start = (WIDTH - total_dots_w) // 2
    for i in range(total_scenes):
        cx = dot_x_start + i * dot_spacing + dot_r
        cy = 70
        color = (255, 220, 50, 255) if i + 1 == scene_number else (180, 180, 180, 160)
        draw.ellipse([(cx - dot_r, cy - dot_r), (cx + dot_r, cy + dot_r)], fill=color)

    # Convert to RGB numpy array for moviepy
    rgb = Image.new("RGB", (WIDTH, HEIGHT))
    rgb.paste(canvas, mask=canvas.split()[3])
    return np.array(rgb)


def _crop_center(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center-crop + scale an image to exact target dimensions."""
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


class VideoAgent:
    def assemble_video(
        self,
        script: dict,
        image_paths: list[Path],
        audio_paths: list[Path],
        workspace: Path,
    ) -> Path:
        """
        Assembles the final MP4 from images + audio clips.
        Each scene clip = background image + TTS audio, exact duration.
        Appends an outro scene using the last image.
        Returns path to the final MP4 file.
        """
        scenes = script["scenes"]
        total_scenes = len(scenes)
        clips = []

        logger.info("Assembling video scenes...")

        for i, scene in enumerate(scenes):
            n = scene["scene_number"]
            img_path = image_paths[i]
            aud_path = audio_paths[i]
            on_text = scene["on_screen_text"]

            logger.info(f"  Scene {n}/{total_scenes} ...")

            # Load audio to get exact duration
            audio_clip = AudioFileClip(str(aud_path))
            duration = audio_clip.duration + 0.4  # tiny tail silence

            # Render frame
            frame = _render_frame(img_path, on_text, n, total_scenes)

            # Build image clip
            img_clip = (
                ImageClip(frame)
                .set_duration(duration)
                .set_audio(audio_clip)
            )

            # Fade in/out
            img_clip = img_clip.fadein(0.3).fadeout(0.3)
            clips.append(img_clip)

        # --- Outro scene ---
        outro_audio = AudioFileClip(str(audio_paths[-1]))
        outro_frame = _render_frame(
            image_paths[-1],
            "FOLLOW FOR MORE ↑",
            total_scenes,
            total_scenes,
        )
        outro_clip = (
            ImageClip(outro_frame)
            .set_duration(outro_audio.duration + 0.5)
            .set_audio(outro_audio)
            .fadein(0.3)
            .fadeout(0.5)
        )
        clips.append(outro_clip)

        # --- Concatenate ---
        logger.info("Concatenating and encoding final video...")
        final = concatenate_videoclips(clips, method="compose")

        output_path = workspace / "final_video.mp4"
        final.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            bitrate="6000k",
            audio_bitrate="192k",
            preset="fast",
            threads=4,
            logger=None,  # suppress moviepy verbose output
        )

        final.close()
        for c in clips:
            c.close()

        logger.info(f"✓ Video ready: {output_path} ({output_path.stat().st_size // (1024*1024)}MB)")
        return output_path
