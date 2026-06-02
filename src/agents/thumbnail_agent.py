from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import textwrap
import random
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Thumbnail dimensions: YouTube standard
THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720

# Color palettes for different content types
COLOR_PALETTES = {
    "factsunlocked": {
        "bg_colors": [
            (13, 27, 42),      # Deep blue
            (25, 25, 112),     # Midnight blue
            (0, 0, 50),        # Almost black blue
        ],
        "accent_colors": [
            (255, 215, 0),     # Gold
            (0, 255, 200),     # Cyan
            (255, 100, 255),   # Magenta
        ],
        "text_color": (255, 255, 255),  # White
    },
    "astrofacts": {
        "bg_colors": [
            (15, 10, 30),      # Deep purple
            (25, 15, 50),      # Dark purple
            (10, 5, 20),       # Almost black purple
        ],
        "accent_colors": [
            (200, 100, 255),   # Purple
            (100, 200, 255),   # Light blue
            (255, 150, 200),   # Pink
        ],
        "text_color": (255, 255, 255),  # White
    }
}

# Zodiac symbols for AstroFacts
ZODIAC_SYMBOLS = {
    "Aries": "♈",
    "Taurus": "♉",
    "Gemini": "♊",
    "Cancer": "♋",
    "Leo": "♌",
    "Virgo": "♍",
    "Libra": "♎",
    "Scorpio": "♏",
    "Sagittarius": "♐",
    "Capricorn": "♑",
    "Aquarius": "♒",
    "Pisces": "♓",
}


class ThumbnailAgent:
    def __init__(self, channel: str = "factsunlocked"):
        """
        Initialize thumbnail generator.
        
        Args:
            channel: "factsunlocked" or "astrofacts"
        """
        self.channel = channel
        self.palette = COLOR_PALETTES.get(channel, COLOR_PALETTES["factsunlocked"])
        
        # Try to load a bold font, fall back to default if not available
        try:
            self.font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
            self.font_subtitle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
            self.font_accent = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
        except (OSError, TypeError):
            # Fall back to default font
            self.font_title = ImageFont.load_default()
            self.font_subtitle = ImageFont.load_default()
            self.font_accent = ImageFont.load_default()

    def generate(
        self,
        title: str,
        subtitle: str = None,
        channel_tag: str = None,
        metadata: dict = None,
        output_path: str = None,
    ) -> str:
        """
        Generate a high-impact thumbnail.
        
        Args:
            title: Main text (e.g., "5 Facts NASA Won't Tell You")
            subtitle: Secondary text (optional, e.g., "Mind Blowing")
            channel_tag: Optional tag (e.g., zodiac sign or emoji)
            metadata: Optional dict with extra context (for astrofacts: period, sign)
            output_path: Where to save the thumbnail (if None, auto-generate)
            
        Returns:
            Path to the generated thumbnail
        """
        # Auto-generate output path if not provided
        if output_path is None:
            output_path = Path.cwd() / "workspace" / "thumbnail.png"
        else:
            output_path = Path(output_path)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create image with random background gradient
        img = self._create_gradient_bg()

        # Draw accent elements
        self._draw_accent_elements(img, metadata or {})

        # Draw main title
        self._draw_title(img, title)

        # Draw subtitle if provided
        if subtitle:
            self._draw_subtitle(img, subtitle)

        # Draw channel tag (emoji or zodiac symbol)
        if channel_tag:
            self._draw_channel_tag(img, channel_tag, metadata or {})

        # Save
        img.save(str(output_path), "PNG", quality=95)
        logger.info(f"✅ Thumbnail generated → {output_path}")
        return str(output_path)

    def _create_gradient_bg(self) -> Image.Image:
        """Create a gradient background."""
        bg_color = random.choice(self.palette["bg_colors"])
        accent_color = random.choice(self.palette["accent_colors"])
        
        img = Image.new("RGB", (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img, "RGBA")

        # Draw subtle gradient overlay using rectangles
        for y in range(THUMBNAIL_HEIGHT):
            alpha = int((y / THUMBNAIL_HEIGHT) * 100)
            blend = tuple(
                int(bg_color[i] + (accent_color[i] - bg_color[i]) * (y / THUMBNAIL_HEIGHT))
                for i in range(3)
            )
            draw.line([(0, y), (THUMBNAIL_WIDTH, y)], fill=blend, width=1)

        return img

    def _draw_accent_elements(self, img: Image.Image, metadata: dict):
        """Draw accent shapes (circles, stars) to attract attention."""
        draw = ImageDraw.Draw(img, "RGBA")
        accent_color = random.choice(self.palette["accent_colors"])

        # Draw 2-3 accent circles in corners
        circle_size = 150
        positions = [
            (THUMBNAIL_WIDTH - circle_size, 0),
            (0, THUMBNAIL_HEIGHT - circle_size),
        ]

        for x, y in positions:
            draw.ellipse(
                [x, y, x + circle_size, y + circle_size],
                fill=(*accent_color, 30),
                outline=(*accent_color, 100),
                width=3
            )

    def _draw_title(self, img: Image.Image, title: str):
        """Draw the main title text with drop shadow."""
        draw = ImageDraw.Draw(img, "RGBA")
        
        # Wrap text to fit
        max_chars = 18
        wrapped = "\n".join(textwrap.wrap(title, width=max_chars))

        # Get text bounding box
        bbox = draw.textbbox((0, 0), wrapped, font=self.font_title)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Center horizontally, place in upper-middle
        x = (THUMBNAIL_WIDTH - text_width) // 2
        y = (THUMBNAIL_HEIGHT - text_height) // 2 - 80

        # Draw shadow
        draw.text((x + 3, y + 3), wrapped, font=self.font_title, fill=(0, 0, 0, 200))

        # Draw main text
        draw.text((x, y), wrapped, font=self.font_title, fill=self.palette["text_color"])

    def _draw_subtitle(self, img: Image.Image, subtitle: str):
        """Draw subtitle text."""
        draw = ImageDraw.Draw(img, "RGBA")
        accent_color = random.choice(self.palette["accent_colors"])

        bbox = draw.textbbox((0, 0), subtitle, font=self.font_subtitle)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (THUMBNAIL_WIDTH - text_width) // 2
        y = THUMBNAIL_HEIGHT - 150

        # Draw with accent color
        draw.text((x + 2, y + 2), subtitle, font=self.font_subtitle, fill=(0, 0, 0, 150))
        draw.text((x, y), subtitle, font=self.font_subtitle, fill=accent_color)

    def _draw_channel_tag(self, img: Image.Image, channel_tag: str, metadata: dict):
        """Draw zodiac symbol or emoji in top-right."""
        draw = ImageDraw.Draw(img, "RGBA")
        accent_color = random.choice(self.palette["accent_colors"])

        # For astrofacts, use zodiac symbol
        if self.channel == "astrofacts" and metadata.get("sign"):
            symbol = ZODIAC_SYMBOLS.get(metadata["sign"], "✨")
        else:
            symbol = channel_tag

        bbox = draw.textbbox((0, 0), symbol, font=self.font_accent)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = THUMBNAIL_WIDTH - text_width - 30
        y = 30

        # Draw with glow effect
        draw.text((x + 2, y + 2), symbol, font=self.font_accent, fill=(0, 0, 0, 100))
        draw.text((x, y), symbol, font=self.font_accent, fill=accent_color)
