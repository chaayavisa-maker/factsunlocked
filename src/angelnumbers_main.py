"""
AngelNumbers Pipeline Orchestrator
Uses the same class-based agents as FactsUnlocked/AstroFacts, with AngelNumbers settings.

Modes:
  default                        — generate all 12 numbers, save manifest
  --publish-only <manifest_path> — publish from a previous generate run
  --number <Number>              — single number only (generate only, unless --dev)
  --dev --number <Number>        — generate + publish a single number locally

Platform flags (can be combined):
  --skip-youtube                 — skip YouTube publishing
  --skip-tiktok                  — skip TikTok publishing
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

from config.angel_numbers        import ANGEL_NUMBERS, NUMBER_SYMBOLS
from src.agents.image_agent      import ImageAgent
from src.agents.narration_agent  import NarrationAgent
from src.agents.video_agent      import VideoAgent
from src.agents.music_agent      import MusicAgent
from src.agents.numerology_script_agent import generate_numerology_script, generate_seo_metadata
from src.agents.thumbnail_agent  import ThumbnailAgent
from src.platforms.youtube       import upload_video
from src.utils.logger            import get_logger

logger = get_logger("angelnumbers")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

ANGEL_CFG   = CONFIG["channels"]["angelnumbers"]
SETTINGS    = {
    "channel": ANGEL_CFG["channel"],
    "video":   ANGEL_CFG["video"],
    "tts":     ANGEL_CFG["tts"],
}
API_KEY_ENV = ANGEL_CFG["groq_api_key_env"]   # "GROQ_API_KEY_ANGEL"
YT_CFG      = ANGEL_CFG["platforms"]["youtube"]
TIKTOK_CFG  = ANGEL_CFG["platforms"]["tiktok"]
WORKSPACE   = Path(CONFIG["video"]["workspace_dir"])

PERIOD = "daily"  # AngelNumbers launches with daily content only


def default_reference_date() -> date:
    return date.today() + timedelta(days=1)


# ── THUMBNAIL HELPER ──────────────────────────────────────────────────────────

def _generate_angel_thumbnail(number: str, seo: dict, ws: Path) -> str:
    symbol = NUMBER_SYMBOLS.get(number, "✨")
    thumb_title = f"{symbol} {number}\nAngel Number"
    subtitle = seo.get("hook", f"What {number} means for you")[:40]

    thumb_path = ThumbnailAgent(channel="angelnumbers").generate(
        title=thumb_title,
        subtitle=subtitle,
        channel_tag=symbol,
        metadata={"number": number},
        output_path=str(ws / "thumbnail.png"),
    )
    logger.info(f"🖼  Thumbnail → {thumb_path}")
    return thumb_path


# ── GENERATE ─────────────────────────────────────────────────────────────────

async def generate_number(number: str, reference_date: date) -> dict:
    """Full generation pipeline for one angel number. Does NOT publish."""
    run_id = f"angelnumbers_{number}_{reference_date.isoformat()}_{uuid.uuid4().hex[:6]}"
    ws = WORKSPACE / run_id
    ws.mkdir(parents=True, exist_ok=True)
    symbol = NUMBER_SYMBOLS.get(number, "✨")

    logger.info("=" * 60)
    logger.info(f"  GENERATE | {symbol} {number}")
    logger.info(f"  Content for: {reference_date}  (run date: {date.today()})")
    logger.info("=" * 60)

    # 1. Script
    script = generate_numerology_script(
        number, PERIOD, api_key_env=API_KEY_ENV, reference_date=reference_date,
    )

    # ── Adapt script format to what the shared agents expect ─────────────────
    scenes = script.get("scenes", [])
    script["image_queries"] = (
        [f"glowing number {number}, ethereal cosmic light, mystical, cinematic, 8K, portrait"]
        + [s.get("image_prompt", f"angel number {number}, mystical cosmic energy, ethereal light")
           for s in scenes]
        + [f"number {number} illuminated, divine golden light rays, deep space, cinematic, portrait"]
    )
    script.setdefault("payoff", script.get("closing_cta", ""))
    script.setdefault("outro", "Subscribe for a new angel number meaning every single day!")
    # ─────────────────────────────────────────────────────────────────────────

    # 2. SEO metadata
    seo = generate_seo_metadata(number, PERIOD, script, api_key_env=API_KEY_ENV)

    # 3. Thumbnail (generated before images so it can be prepended)
    thumbnail_path = _generate_angel_thumbnail(number, seo, ws)

    # 4. Images
    scene_image_paths = ImageAgent(SETTINGS).generate_all(script, ws)
    if not scene_image_paths:
        raise RuntimeError(f"No images generated for {number}")

    image_paths = [thumbnail_path] + scene_image_paths

    # 5. Narration
    narration_path, scene_durations = await NarrationAgent(SETTINGS).generate(script, ws)

    THUMBNAIL_HOLD = 2.0
    scene_durations_with_thumb = [THUMBNAIL_HOLD] + list(scene_durations)

    # 6. Music
    music_path = MusicAgent(SETTINGS).get_track(ws)

    # 7. Video
    hook_text = f"{symbol} {number} Angel Number"
    final_path = VideoAgent(SETTINGS).assemble(
        workspace=str(ws),
        image_paths=image_paths,
        narration_path=str(narration_path),
        music_path=music_path,
        script=script,
        scene_durations=scene_durations_with_thumb,
        hook_text=hook_text,
    )

    music_credit = MusicAgent.get_credit() if music_path else ""
    metadata = {
        "run_id":         run_id,
        "number":         number,
        "reference_date": reference_date.isoformat(),
        "title":          f"{number} Angel Number — {reference_date.isoformat()}",
        "description":    seo.get("description", "") + (f"\n\n{music_credit}" if music_credit else ""),
        "tags":           seo.get("tags", []),
        "video_path":     final_path,
        "thumbnail_path": thumbnail_path,
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata → {meta_path}")
    return metadata


async def generate_all_numbers(reference_date: date) -> list[dict]:
    logger.info(f"🔢 GENERATE — daily batch for all {len(ANGEL_NUMBERS)} angel numbers")
    results, errors = [], []

    for number in ANGEL_NUMBERS:
        try:
            results.append(await generate_number(number, reference_date))
        except Exception as e:
            logger.error(f"❌ Generate failed for {number}: {e}", exc_info=True)
            errors.append(number)

    manifest_path = WORKSPACE / f"manifest_angelnumbers_daily_{reference_date.isoformat()}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(
        {
            "reference_date": reference_date.isoformat(),
            "runs":           [r["run_id"] for r in results],
            "failed":         errors,
        },
        indent=2,
    ))
    logger.info(f"Manifest → {manifest_path}")
    logger.info(f"Generate complete — {len(results)}/{len(ANGEL_NUMBERS)} succeeded")
    if errors:
        logger.error(f"Failed numbers: {errors}")
    return results


# ── PUBLISH ──────────────────────────────────────────────────────────────────

def publish_number(metadata: dict, skip_youtube: bool = False, skip_tiktok: bool = False) -> dict:
    number     = metadata["number"]
    video_path = Path(metadata["video_path"])

    logger.info("=" * 60)
    logger.info(f"  PUBLISH | {NUMBER_SYMBOLS.get(number, '✨')} {number}")
    logger.info(f"  YouTube: {'SKIP' if skip_youtube else 'enabled'} | TikTok: {'SKIP' if skip_tiktok else 'enabled'}")
    logger.info("=" * 60)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\nMake sure the generate artifact was downloaded first."
        )

    platform_ids = {}

    if YT_CFG.get("enabled") and not skip_youtube:
        number_playlist = YT_CFG.get("number_playlist_ids", {}).get(number, "")
        playlist_id = number_playlist if number_playlist.strip() else None

        pinned_comment = "Which part of this resonated with you? Drop a 🔢 below!"

        yt_id = upload_video(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            category_id=YT_CFG.get("category_id", "22"),
            privacy=YT_CFG.get("privacy", "public"),
            made_for_kids=YT_CFG.get("made_for_kids", False),
            thumbnail_path=metadata.get("thumbnail_path"),
            playlist_id=playlist_id,
            pinned_comment=pinned_comment,
            client_id_env="YOUTUBE_CLIENT_ID_ANGEL",
            client_secret_env="YOUTUBE_CLIENT_SECRET_ANGEL",
            refresh_token_env="YOUTUBE_REFRESH_TOKEN_ANGEL",
        )
        platform_ids["youtube"] = yt_id
        logger.info(f"YouTube ✅ https://youtube.com/shorts/{yt_id}")
    elif skip_youtube:
        logger.info("YouTube ⏭️  skipped")

    if TIKTOK_CFG.get("enabled") and not skip_tiktok:
        from src.platforms.tiktok import upload_video_tiktok
        tt_id = upload_video_tiktok(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
        )
        platform_ids["tiktok"] = tt_id
        logger.info(f"TikTok ✅ publish_id={tt_id}")
    elif skip_tiktok:
        logger.info("TikTok ⏭️  skipped")

    logger.info(f"✅ Published {number}: {platform_ids}")
    return {**metadata, "platform_ids": platform_ids}


def publish_from_manifest(
    manifest_path: Path,
    number: str = None,
    skip_youtube: bool = False,
    skip_tiktok: bool = False,
) -> None:
    manifest = json.loads(manifest_path.read_text())
    run_ids = manifest["runs"]

    logger.info(f"🚀 PUBLISH — angelnumbers daily from manifest ({len(run_ids)} runs)")
    errors = []

    for run_id in run_ids:
        meta_path = WORKSPACE / run_id / "metadata.json"
        if not meta_path.exists():
            logger.error(f"metadata.json missing for run_id={run_id} — skipping")
            errors.append(run_id)
            continue
        metadata = json.loads(meta_path.read_text())
        if number and metadata.get("number", "") != number:
            continue
        try:
            publish_number(metadata, skip_youtube=skip_youtube, skip_tiktok=skip_tiktok)
        except Exception as e:
            logger.error(f"❌ Publish failed for {run_id}: {e}", exc_info=True)
            errors.append(run_id)

    if errors:
        logger.error(f"Failed run_ids: {errors}")
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AngelNumbers pipeline")
    parser.add_argument("--number", choices=ANGEL_NUMBERS, default=None)
    parser.add_argument("--publish-only", metavar="MANIFEST_PATH", nargs="?", const=None, default=None)
    parser.add_argument("--dev", action="store_true", help="Generate + publish (local dev)")
    parser.add_argument("--skip-youtube", action="store_true")
    parser.add_argument("--skip-tiktok", action="store_true")
    parser.add_argument("--reference-date", metavar="YYYY-MM-DD", default=None)
    args = parser.parse_args()

    if args.publish_only is not None and not args.publish_only.strip():
        args.publish_only = None

    number       = args.number
    skip_youtube = args.skip_youtube
    skip_tiktok  = args.skip_tiktok

    if args.reference_date:
        try:
            reference_date = date.fromisoformat(args.reference_date)
        except ValueError:
            logger.error(f"Invalid --reference-date '{args.reference_date}'. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        reference_date = default_reference_date()

    logger.info(f"📅 Reference date (content for): {reference_date}")

    if args.publish_only:
        publish_from_manifest(
            Path(args.publish_only), number=number,
            skip_youtube=skip_youtube, skip_tiktok=skip_tiktok,
        )
    elif args.dev and number:
        metadata = asyncio.run(generate_number(number, reference_date))
        publish_number(metadata, skip_youtube=skip_youtube, skip_tiktok=skip_tiktok)
    elif number:
        metadata = asyncio.run(generate_number(number, reference_date))
        manifest_path = WORKSPACE / f"manifest_angelnumbers_daily_{reference_date.isoformat()}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(
            {"reference_date": reference_date.isoformat(), "runs": [metadata["run_id"]], "failed": []},
            indent=2,
        ))
        logger.info(f"Manifest → {manifest_path}")
    else:
        asyncio.run(generate_all_numbers(reference_date))


if __name__ == "__main__":
    main()
