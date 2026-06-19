"""
AstroFacts Pipeline Orchestrator
Uses the same class-based agents as FactsUnlocked, with AstroFacts settings.

Modes:
  default                        — generate all 12 signs, save manifest
  --publish-only <manifest_path> — publish from a previous generate run
  --sign <Sign>                  — single sign only (generate only, unless --dev)
  --dev --sign <Sign>            — generate + publish a single sign locally

Platform flags (can be combined):
  --skip-youtube                 — skip YouTube publishing
  --skip-tiktok                  — skip TikTok publishing

Date control:
  --reference-date YYYY-MM-DD    — the date the content is FOR (publish date).
                                   Defaults to tomorrow for daily, next Monday
                                   for weekly, 1st of next month for monthly,
                                   and next Jan 1st for yearly.
                                   Override this in CI via the workflow's
                                   computed target date.
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

from config.zodiac               import ZODIAC_SIGNS, SIGN_SYMBOLS
from src.agents.image_agent      import ImageAgent
from src.agents.narration_agent  import NarrationAgent
from src.agents.video_agent      import VideoAgent
from src.agents.music_agent      import MusicAgent
from src.agents.horoscope_script_agent import generate_horoscope_script, generate_seo_metadata
from src.agents.thumbnail_agent  import ThumbnailAgent          # ← NEW
from src.platforms.youtube       import upload_video
from src.utils.logger            import get_logger

logger = get_logger("astrofacts")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

ASTRO_CFG   = CONFIG["channels"]["astrofacts"]
SETTINGS    = {                    # shape the original agents expect
    "channel": ASTRO_CFG["channel"],
    "video":   ASTRO_CFG["video"],
    "tts":     ASTRO_CFG["tts"],
}
API_KEY_ENV = ASTRO_CFG["groq_api_key_env"]   # "GROQ_API_KEY_ASTRO"
YT_CFG      = ASTRO_CFG["platforms"]["youtube"]
TIKTOK_CFG  = ASTRO_CFG["platforms"]["tiktok"]
WORKSPACE   = Path(CONFIG["video"]["workspace_dir"])


def default_reference_date(period: str) -> date:
    """
    Return the natural publish date for content generated today.
    This is what the workflow cron is aligned to:
      daily   → tomorrow
      weekly  → next Monday
      monthly → 1st of next month
      yearly  → January 1st of next year
    """
    today = date.today()
    if period == "daily":
        return today + timedelta(days=1)
    elif period == "weekly":
        # days until next Monday (weekday 0); if today is Sunday (6) → 1 day ahead
        days_ahead = (0 - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    elif period == "monthly":
        # 1st of next month
        if today.month == 12:
            return date(today.year + 1, 1, 1)
        return date(today.year, today.month + 1, 1)
    elif period == "yearly":
        return date(today.year + 1, 1, 1)
    return today + timedelta(days=1)


# ── THUMBNAIL HELPERS ─────────────────────────────────────────────────────────

def _generate_astro_thumbnail(sign: str, period: str, seo: dict, ws: Path) -> str:
    """
    Generate a branded AstroFacts thumbnail and return its path.

    The thumbnail is ALSO injected as image_paths[0] so the very first frame
    of every video is the channel thumbnail — maximising brand recognition
    in feed previews and when viewers screenshot the opening frame.
    """
    symbol = SIGN_SYMBOLS.get(sign, "✨")
    period_label = period.title()

    # Title shown on thumbnail: short, punchy, keyword-rich
    thumb_title = f"{symbol} {sign}\n{period_label} Horoscope"
    subtitle = seo.get("hook", f"What the stars say for {sign}")[:40]

    thumb_path = ThumbnailAgent(channel="astrofacts").generate(
        title=thumb_title,
        subtitle=subtitle,
        channel_tag=symbol,
        metadata={"sign": sign, "period": period},
        output_path=str(ws / "thumbnail.png"),
    )
    logger.info(f"🖼  Thumbnail → {thumb_path}")
    return thumb_path


# ── GENERATE ─────────────────────────────────────────────────────────────────

async def generate_sign(sign: str, period: str, reference_date: date) -> dict:
    """Full generation pipeline for one (sign, period). Does NOT publish.

    reference_date: the date the content is FOR (the publish date), not the
                    run date. Planetary positions are computed for this date.
    """
    run_id = (
        f"astrofacts_{period}_{sign.lower()}"
        f"_{reference_date.isoformat()}_{uuid.uuid4().hex[:6]}"
    )
    ws = WORKSPACE / run_id
    ws.mkdir(parents=True, exist_ok=True)
    symbol = SIGN_SYMBOLS.get(sign, "✨")

    logger.info("=" * 60)
    logger.info(f"  GENERATE | {symbol} {sign} | {period.upper()}")
    logger.info(f"  Content for: {reference_date}  (run date: {date.today()})")
    logger.info("=" * 60)

    # 1. Script — pass reference_date so planetary positions are for publish day
    script = generate_horoscope_script(
        sign, period,
        api_key_env=API_KEY_ENV,
        reference_date=reference_date,
    )

    # ── Adapt horoscope script format to what the shared agents expect ────────
    from config.zodiac import SIGN_ELEMENTS
    element = SIGN_ELEMENTS.get(sign, "cosmic")
    scenes  = script.get("scenes", [])
    script["image_queries"] = (
        [f"{sign} zodiac {symbol}, cosmic {element} energy, glowing constellation, "
         f"ethereal nebula, mystical stars, cinematic, 8K, portrait"]
        + [s.get("image_prompt",
                  f"cosmic {sign} astrology, {element} element energy, ethereal light, mystical")
           for s in scenes]
        + [f"{sign} constellation illuminated, divine golden light rays, deep space, "
           f"mystical fortune, cosmic energy, cinematic, portrait"]
    )
    script.setdefault("payoff", script.get("closing_cta", ""))
    script.setdefault("outro", f"Subscribe for your {sign} horoscope every single day!")
    # ─────────────────────────────────────────────────────────────────────────

    # 2. SEO metadata  (generated early so we can use the hook on the thumbnail)
    seo = generate_seo_metadata(sign, period, script, api_key_env=API_KEY_ENV)

    # 3. Thumbnail  ← generated BEFORE images so we can prepend it
    thumbnail_path = _generate_astro_thumbnail(sign, period, seo, ws)

    # 4. Images — AI-generated scene images
    scene_image_paths = ImageAgent(SETTINGS).generate_all(script, ws)
    if not scene_image_paths:
        raise RuntimeError(f"No images generated for {sign} {period}")

    # ── KEY CHANGE: prepend thumbnail as the very first frame ─────────────────
    # This means the thumbnail IS the opening image of the video.
    # When YouTube auto-generates a preview it often picks the first frame,
    # so subscribers see a consistent, branded frame every time.
    image_paths = [thumbnail_path] + scene_image_paths
    # ─────────────────────────────────────────────────────────────────────────

    # 5. Narration → (combined_audio, scene_durations)
    narration_path, scene_durations = await NarrationAgent(SETTINGS).generate(script, ws)

    # Pad scene_durations to match the extra thumbnail frame (2-second hold)
    THUMBNAIL_HOLD = 2.0
    scene_durations_with_thumb = [THUMBNAIL_HOLD] + list(scene_durations)

    # 6. Music
    music_path = MusicAgent(SETTINGS).get_track(ws)

    # 7. Video — thumbnail frame + scene frames
    hook_text = f"{symbol} {sign} {period.title()} Horoscope"
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
        "sign":           sign,
        "period":         period,
        "reference_date": reference_date.isoformat(),   # publish date, for auditability
        "title":          f"{sign} {period.title()} {reference_date.isoformat()} Horoscope",
        "description":    seo.get("description", "") + (f"\n\n{music_credit}" if music_credit else ""),
        "tags":           seo.get("tags", []),
        "video_path":     final_path,
        "thumbnail_path": thumbnail_path,               # ← stored for YouTube upload
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata → {meta_path}")
    return metadata


async def generate_all_signs(period: str, reference_date: date) -> list[dict]:
    logger.info(f"🔮 GENERATE — {period.upper()} batch for all 12 signs")
    logger.info(f"   Content for: {reference_date}  (run date: {date.today()})")
    results, errors = [], []

    for sign in ZODIAC_SIGNS:
        try:
            results.append(await generate_sign(sign, period, reference_date))
        except Exception as e:
            logger.error(f"❌ Generate failed for {sign}: {e}", exc_info=True)
            errors.append(sign)

    # Name the manifest after the reference (publish) date, not the run date
    manifest_path = WORKSPACE / f"manifest_{period}_{reference_date.isoformat()}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(
        {
            "period":         period,
            "reference_date": reference_date.isoformat(),
            "runs":           [r["run_id"] for r in results],
            "failed":         errors,
        },
        indent=2,
    ))
    logger.info(f"Manifest → {manifest_path}")
    logger.info(f"Generate complete — {len(results)}/12 succeeded")
    if errors:
        logger.error(f"Failed signs: {errors}")
    return results


# ── PUBLISH ──────────────────────────────────────────────────────────────────

def publish_sign(metadata: dict, skip_youtube: bool = False, skip_tiktok: bool = False) -> dict:
    """Upload one sign's video to YouTube and/or TikTok."""
    sign       = metadata["sign"]
    period     = metadata["period"]
    video_path = Path(metadata["video_path"])

    logger.info("=" * 60)
    logger.info(f"  PUBLISH | {SIGN_SYMBOLS.get(sign,'✨')} {sign} | {period.upper()}")
    logger.info(f"  YouTube: {'SKIP' if skip_youtube else 'enabled'} | TikTok: {'SKIP' if skip_tiktok else 'enabled'}")
    logger.info("=" * 60)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\n"
            "Make sure the generate artifact was downloaded first."
        )

    platform_ids = {}

    # ── YouTube ──────────────────────────────────────────────────────────────
    if YT_CFG.get("enabled") and not skip_youtube:
        # Multi-playlist: add to both the period playlist AND the sign-specific playlist
        period_playlist = YT_CFG.get("playlist_ids", {}).get(period, "")
        sign_playlist   = YT_CFG.get("sign_playlist_ids", {}).get(sign, "")
        playlist_ids    = [p for p in [period_playlist, sign_playlist] if p and p.strip()]
        playlist_id     = playlist_ids if playlist_ids else None

        # Pinned comment — drives early engagement signals in the first hour
        _PINNED_COMMENTS = {
            "daily":   "Did this resonate? Drop a ⭐ below and tell me which part hit different!",
            "weekly":  "Which part of this week's reading are you most focused on? 👇",
            "monthly": "What's the ONE thing you're calling in this month? Share it below 🌙",
            "yearly":  "What's your biggest intention for this year? Drop it below ✨",
        }

        yt_id = upload_video(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            category_id=YT_CFG.get("category_id", "22"),
            privacy=YT_CFG.get("privacy", "public"),
            made_for_kids=YT_CFG.get("made_for_kids", False),
            thumbnail_path=metadata.get("thumbnail_path"),   # ← now always passed
            playlist_id=playlist_id,
            pinned_comment=_PINNED_COMMENTS.get(period, ""),
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
        )
        platform_ids["tiktok"] = tt_id
        logger.info(f"TikTok ✅ publish_id={tt_id}")
    elif skip_tiktok:
        logger.info("TikTok ⏭️  skipped")

    logger.info(f"✅ Published {sign} {period}: {platform_ids}")
    return {**metadata, "platform_ids": platform_ids}


def publish_from_manifest(
    manifest_path: Path,
    sign: str = None,
    skip_youtube: bool = False,
    skip_tiktok: bool = False,
) -> None:
    manifest = json.loads(manifest_path.read_text())
    period   = manifest["period"]
    run_ids  = manifest["runs"]

    logger.info(f"🚀 PUBLISH — {period.upper()} from manifest ({len(run_ids)} runs)")
    logger.info(f"   YouTube: {'SKIP' if skip_youtube else 'enabled'} | TikTok: {'SKIP' if skip_tiktok else 'enabled'}")
    errors = []

    for run_id in run_ids:
        meta_path = WORKSPACE / run_id / "metadata.json"
        if not meta_path.exists():
            logger.error(f"metadata.json missing for run_id={run_id} — skipping")
            errors.append(run_id)
            continue
        metadata = json.loads(meta_path.read_text())
        if sign and metadata.get("sign", "").lower() != sign.lower():
            continue
        try:
            publish_sign(metadata, skip_youtube=skip_youtube, skip_tiktok=skip_tiktok)
        except Exception as e:
            logger.error(f"❌ Publish failed for {run_id}: {e}", exc_info=True)
            errors.append(run_id)

    if errors:
        logger.error(f"Failed run_ids: {errors}")
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AstroFacts pipeline")
    parser.add_argument("--period", choices=["daily","weekly","monthly","yearly"], required=True)
    parser.add_argument("--sign",   choices=ZODIAC_SIGNS + [s.lower() for s in ZODIAC_SIGNS], default=None)
    parser.add_argument("--publish-only", metavar="MANIFEST_PATH", nargs="?", const=None, default=None)
    parser.add_argument("--dev", action="store_true", help="Generate + publish (local dev)")
    parser.add_argument("--skip-youtube", action="store_true", help="Skip YouTube publishing")
    parser.add_argument("--skip-tiktok",  action="store_true", help="Skip TikTok publishing")
    parser.add_argument(
        "--reference-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "The date the content is FOR (publish date). "
            "Planetary positions are computed for this date. "
            "Defaults to the natural next publish date for the given period "
            "(tomorrow for daily, next Monday for weekly, etc.)."
        ),
    )
    args = parser.parse_args()

    if hasattr(args, 'publish_only') and args.publish_only is not None and not args.publish_only.strip():
        args.publish_only = None

    period       = args.period
    sign         = args.sign.title() if args.sign else None
    skip_youtube = args.skip_youtube
    skip_tiktok  = args.skip_tiktok

    # Resolve reference date: CLI arg → smart default
    if args.reference_date:
        try:
            reference_date = date.fromisoformat(args.reference_date)
        except ValueError:
            logger.error(f"Invalid --reference-date '{args.reference_date}'. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        reference_date = default_reference_date(period)

    logger.info(f"📅 Reference date (content for): {reference_date}")

    if args.publish_only:
        publish_from_manifest(
            Path(args.publish_only),
            sign=sign,
            skip_youtube=skip_youtube,
            skip_tiktok=skip_tiktok,
        )

    elif args.dev and sign:
        metadata = asyncio.run(generate_sign(sign, period, reference_date))
        publish_sign(metadata, skip_youtube=skip_youtube, skip_tiktok=skip_tiktok)

    elif sign:
        metadata = asyncio.run(generate_sign(sign, period, reference_date))
        manifest_path = WORKSPACE / f"manifest_{period}_{reference_date.isoformat()}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(
            {
                "period":         period,
                "reference_date": reference_date.isoformat(),
                "runs":           [metadata["run_id"]],
                "failed":         [],
            },
            indent=2,
        ))
        logger.info(f"Manifest → {manifest_path}")

    else:
        asyncio.run(generate_all_signs(period, reference_date))


if __name__ == "__main__":
    main()
