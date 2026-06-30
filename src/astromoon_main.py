"""
AstroMoon Pipeline — "Moon & Stars Weekly" extension for astrounlocked channel.

Generates one collective Moon energy video per week tied to the current moon phase.

Usage:
  python src/astromoon_main.py --period weekly
  python src/astromoon_main.py --period weekly --dev               # generate + publish
  python src/astromoon_main.py --period weekly --reference-date 2026-07-01
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.image_agent          import ImageAgent
from src.agents.narration_agent      import NarrationAgent
from src.agents.video_agent          import VideoAgent
from src.agents.music_agent          import MusicAgent
from src.agents.moon_script_agent    import generate_moon_script, generate_moon_seo, MOON_THEMES
from src.agents.thumbnail_agent      import ThumbnailAgent
from src.platforms.youtube           import upload_video
from src.utils.logger                import get_logger

logger = get_logger("astromoon")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

# Re-use the astrofacts channel credentials & style
ASTRO_CFG   = CONFIG["channels"]["astrofacts"]
SETTINGS    = {
    "channel": ASTRO_CFG["channel"],
    "video":   ASTRO_CFG["video"],
    "tts":     ASTRO_CFG["tts"],
}
API_KEY_ENV = ASTRO_CFG["groq_api_key_env"]
YT_CFG      = ASTRO_CFG["platforms"]["youtube"]
WORKSPACE   = Path(CONFIG["video"]["workspace_dir"])

THUMBNAIL_HOLD = 3.0  # Moon videos: hold thumbnail 1s longer for brand impact


async def generate_moon_video(reference_date: date) -> dict:
    run_id = f"astromoon_weekly_{reference_date.isoformat()}_{uuid.uuid4().hex[:6]}"
    ws = WORKSPACE / run_id
    ws.mkdir(parents=True, exist_ok=True)

    # 1. Script (auto-detects moon phase)
    script = generate_moon_script(for_date=reference_date, api_key_env=API_KEY_ENV)
    moon_phase = script["moon_phase"]
    emoji      = script["moon_emoji"]

    logger.info("=" * 60)
    logger.info(f"  ASTROMOON | {emoji} {moon_phase} | Weekly")
    logger.info(f"  Content for: {reference_date}")
    logger.info("=" * 60)

    # 2. SEO
    seo = generate_moon_seo(moon_phase, script, api_key_env=API_KEY_ENV)

    # 3. Thumbnail — moon phase emoji as channel_tag
    thumb_title = f"{emoji} {moon_phase}\nWeekly Energy"
    thumbnail_path = ThumbnailAgent(channel="astrofacts").generate(
        title=thumb_title,
        subtitle="What the stars say this week",
        channel_tag=emoji,
        metadata={"sign": moon_phase},
        output_path=str(ws / "thumbnail.png"),
    )

    # 4. Scene images
    scene_image_paths = ImageAgent(SETTINGS).generate_all(script, ws)
    if not scene_image_paths:
        raise RuntimeError("No images generated for moon video")

    # Thumbnail as first frame
    image_paths = [thumbnail_path] + scene_image_paths

    # 5. Narration
    narration_path, scene_durations = await NarrationAgent(SETTINGS).generate(script, ws)

    # Prepend thumbnail hold duration
    scene_durations_with_thumb = [THUMBNAIL_HOLD] + list(scene_durations)

    # 6. Music
    music_path = MusicAgent(SETTINGS).get_track(ws)

    # 7. Video
    hook_text = f"{emoji} {moon_phase} Energy"
    final_path = VideoAgent(SETTINGS).assemble(
        workspace=str(ws),
        image_paths=image_paths,
        narration_path=str(narration_path),
        music_path=music_path,
        script=script,
        scene_durations=scene_durations_with_thumb,
        hook_text=hook_text,
        thumbnail_caption="",
    )

    music_credit = MusicAgent.get_credit() if music_path else ""
    metadata = {
        "run_id":         run_id,
        "moon_phase":     moon_phase,
        "reference_date": reference_date.isoformat(),
        "title":          seo.get("title", f"{emoji} {moon_phase} Weekly Energy {reference_date.isoformat()}"),
        "description":    seo.get("description", "") + (f"\n\n{music_credit}" if music_credit else ""),
        "tags":           seo.get("tags", []),
        "video_path":     final_path,
        "thumbnail_path": thumbnail_path,
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata → {meta_path}")
    return metadata


def publish_moon_video(metadata: dict, skip_youtube: bool = False) -> dict:
    video_path = Path(metadata["video_path"])
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    logger.info(f"🚀 PUBLISH Moon video: {metadata['title']}")
    platform_ids = {}

    if YT_CFG.get("enabled") and not skip_youtube:
        # Add to the weekly horoscope playlist
        playlist_id = YT_CFG.get("playlist_ids", {}).get("weekly", "") or None

        yt_id = upload_video(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            category_id=YT_CFG.get("category_id", "22"),
            privacy=YT_CFG.get("privacy", "public"),
            made_for_kids=False,
            thumbnail_path=metadata.get("thumbnail_path"),
            playlist_id=playlist_id,
            pinned_comment="🌕 Drop your moon phase manifestation intention below — let's set it together! 👇",
            client_id_env="YOUTUBE_CLIENT_ID_ASTRO",
            client_secret_env="YOUTUBE_CLIENT_SECRET_ASTRO",
            refresh_token_env="YOUTUBE_REFRESH_TOKEN_ASTRO",
        )
        platform_ids["youtube"] = yt_id
        logger.info(f"YouTube ✅ https://youtube.com/shorts/{yt_id}")

    return {**metadata, "platform_ids": platform_ids}


def main():
    parser = argparse.ArgumentParser(description="AstroMoon pipeline")
    parser.add_argument("--period", choices=["weekly"], default="weekly")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--skip-youtube", action="store_true")
    parser.add_argument("--reference-date", metavar="YYYY-MM-DD", default=None)
    args = parser.parse_args()

    if args.reference_date:
        reference_date = date.fromisoformat(args.reference_date)
    else:
        # Default to next Monday
        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        reference_date = today + timedelta(days=days_ahead)

    logger.info(f"📅 Moon video for: {reference_date}")

    metadata = asyncio.run(generate_moon_video(reference_date))

    if args.dev:
        publish_moon_video(metadata, skip_youtube=args.skip_youtube)


if __name__ == "__main__":
    main()
