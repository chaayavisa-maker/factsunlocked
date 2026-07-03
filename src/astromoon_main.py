"""
AstroMoon Pipeline — "Moon & Stars Weekly" extension for astrounlocked channel.

Generates one collective Moon energy video per week tied to the current moon phase.

Modes (mirrors astrofacts_main.py so every step can be re-run independently):
  default                        — generate only, save manifest
  --publish-only <manifest_path> — publish from a previous generate run
                                    (no regeneration — re-run safely after a
                                    failed/partial publish)
  --dev                          — generate + publish in one go (local dev)

Platform flags (can be combined):
  --skip-youtube                 — skip YouTube publishing
  --skip-tiktok                  — skip TikTok publishing

Usage:
  python src/astromoon_main.py --period weekly
  python src/astromoon_main.py --period weekly --publish-only workspace/manifest_weekly_2026-07-06.json
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
TIKTOK_CFG  = ASTRO_CFG["platforms"]["tiktok"]
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
        "period":         "weekly",
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


def publish_moon_video(metadata: dict, skip_youtube: bool = False, skip_tiktok: bool = False) -> dict:
    video_path = Path(metadata["video_path"])
    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\n"
            "Make sure the generate artifact was downloaded first."
        )

    logger.info("=" * 60)
    logger.info(f"🚀 PUBLISH Moon video: {metadata['title']}")
    logger.info(f"   YouTube: {'SKIP' if skip_youtube else 'enabled'} | TikTok: {'SKIP' if skip_tiktok else 'enabled'}")
    logger.info("=" * 60)
    platform_ids = {}

    # ── YouTube ──────────────────────────────────────────────────────────────
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
    elif skip_youtube:
        logger.info("YouTube ⏭️  skipped")

    # ── TikTok ───────────────────────────────────────────────────────────────
    if TIKTOK_CFG.get("enabled") and not skip_tiktok:
        from src.platforms.tiktok import upload_video_tiktok
        tt_id = upload_video_tiktok(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            client_key_env="TIKTOK_CLIENT_KEY_ASTRO",
            client_secret_env="TIKTOK_CLIENT_SECRET_ASTRO",
            refresh_token_env="TIKTOK_REFRESH_TOKEN_ASTRO",
        )
        platform_ids["tiktok"] = tt_id
        logger.info(f"TikTok ✅ publish_id={tt_id}")
    elif skip_tiktok:
        logger.info("TikTok ⏭️  skipped")

    logger.info(f"✅ Published moon weekly: {platform_ids}")
    return {**metadata, "platform_ids": platform_ids}


def publish_from_manifest(
    manifest_path: Path,
    skip_youtube: bool = False,
    skip_tiktok: bool = False,
) -> None:
    """Re-publish from a manifest written by a previous generate-only run.

    Mirrors astrofacts_main.py's publish_from_manifest() so a failed or
    partial publish step can be safely re-run without regenerating the
    video.
    """
    manifest = json.loads(manifest_path.read_text())
    run_ids  = manifest["runs"]

    logger.info(f"🚀 PUBLISH — Moon Weekly from manifest ({len(run_ids)} run(s))")
    logger.info(f"   YouTube: {'SKIP' if skip_youtube else 'enabled'} | TikTok: {'SKIP' if skip_tiktok else 'enabled'}")
    errors = []

    for run_id in run_ids:
        meta_path = WORKSPACE / run_id / "metadata.json"
        if not meta_path.exists():
            logger.error(f"metadata.json missing for run_id={run_id} — skipping")
            errors.append(run_id)
            continue
        metadata = json.loads(meta_path.read_text())
        try:
            publish_moon_video(metadata, skip_youtube=skip_youtube, skip_tiktok=skip_tiktok)
        except Exception as e:
            logger.error(f"❌ Publish failed for {run_id}: {e}", exc_info=True)
            errors.append(run_id)

    if errors:
        logger.error(f"Failed run_ids: {errors}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="AstroMoon pipeline")
    parser.add_argument("--period", choices=["weekly"], default="weekly")
    parser.add_argument(
        "--publish-only",
        metavar="MANIFEST_PATH",
        nargs="?",
        const=None,
        default=None,
        help=(
            "Re-publish without regenerating. Paste the manifest path from "
            "a previous generate-only run (e.g. "
            "workspace/manifest_weekly_2026-07-06.json). "
            "Leave blank for a full generate (+ publish if --dev) run."
        ),
    )
    parser.add_argument("--dev", action="store_true", help="Generate + publish (local dev)")
    parser.add_argument("--skip-youtube", action="store_true", help="Skip YouTube publishing")
    parser.add_argument("--skip-tiktok",  action="store_true", help="Skip TikTok publishing")
    parser.add_argument("--reference-date", metavar="YYYY-MM-DD", default=None)
    args = parser.parse_args()

    if args.publish_only is not None and not args.publish_only.strip():
        args.publish_only = None

    skip_youtube = args.skip_youtube
    skip_tiktok  = args.skip_tiktok

    if args.reference_date:
        reference_date = date.fromisoformat(args.reference_date)
    else:
        # Default to next Monday
        today = date.today()
        days_ahead = (0 - today.weekday()) % 7 or 7
        reference_date = today + timedelta(days=days_ahead)

    logger.info(f"📅 Moon video for: {reference_date}")

    if args.publish_only:
        publish_from_manifest(
            Path(args.publish_only),
            skip_youtube=skip_youtube,
            skip_tiktok=skip_tiktok,
        )

    elif args.dev:
        metadata = asyncio.run(generate_moon_video(reference_date))
        publish_moon_video(metadata, skip_youtube=skip_youtube, skip_tiktok=skip_tiktok)

    else:
        # Generate-only: write a manifest so a separate publish step
        # (re-runnable on its own) can pick this run up later.
        metadata = asyncio.run(generate_moon_video(reference_date))
        manifest_path = WORKSPACE / f"manifest_weekly_{reference_date.isoformat()}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(
            {
                "period":         "weekly",
                "reference_date": reference_date.isoformat(),
                "runs":           [metadata["run_id"]],
                "failed":         [],
            },
            indent=2,
        ))
        logger.info(f"Manifest → {manifest_path}")


if __name__ == "__main__":
    main()
