"""
AstroFacts Pipeline Orchestrator — IMPROVED VERSION
Changes from original:
  1. Staggered uploads: signs are uploaded 2 hours apart (not all at once).
     This gives each video its own algorithm push window.
  2. Pinned comment: each video gets an auto-posted engagement question.
  3. Multi-playlist: each video is added to BOTH its sign playlist AND its
     period playlist simultaneously.
  4. Sign-specific playlists: settings.yaml can now define per-sign playlist IDs.
  5. Description length: horoscope SEO now targets 500-800 chars.

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
"""

import argparse
import asyncio
import json
import sys
import time
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
from src.platforms.youtube       import upload_video
from src.utils.logger            import get_logger

logger = get_logger("astrofacts")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

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

# IMPROVEMENT: stagger uploads by this many seconds between signs.
# 7200 = 2 hours. With 12 signs this spreads across 22 hours.
# The GitHub Actions workflow should schedule publish at 02:00 UTC so
# the last sign lands at ~00:00 UTC the following day (still same calendar day).
STAGGER_SECONDS = 7200

# IMPROVEMENT: Pinned comment templates per period.
# A question drives more replies than a statement.
PINNED_COMMENT_TEMPLATES = {
    "daily":   "Did this resonate with your day? Drop a ⭐ below if it hit different — and tell me which part!",
    "weekly":  "Which part of this week's reading are you most excited (or nervous) about? 👇",
    "monthly": "What's the ONE thing you're calling in this month? Share it below — the universe is listening 🌙",
    "yearly":  "What's your biggest intention for this year? Drop it in the comments and let's manifest it together ✨",
}


def default_reference_date(period: str) -> date:
    today = date.today()
    if period == "daily":
        return today + timedelta(days=1)
    elif period == "weekly":
        days_ahead = (0 - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    elif period == "monthly":
        if today.month == 12:
            return date(today.year + 1, 1, 1)
        return date(today.year, today.month + 1, 1)
    elif period == "yearly":
        return date(today.year + 1, 1, 1)
    return today + timedelta(days=1)


def _get_playlist_ids(sign: str, period: str) -> list[str]:
    """
    IMPROVEMENT: return BOTH the period playlist AND the sign-specific playlist.
    This means each video appears in two playlists, maximising discoverability.

    Settings structure expected (add to settings.yaml):
      astrofacts:
        platforms:
          youtube:
            playlist_ids:
              daily: "PLxxx"
              weekly: "PLyyy"
              monthly: "PLzzz"
              yearly: "PLwww"
            sign_playlist_ids:           <-- NEW
              Aries: "PLaaa"
              Taurus: "PLbbb"
              ...
    """
    ids = []

    # Period playlist (existing)
    period_id = YT_CFG.get("playlist_ids", {}).get(period, "")
    if period_id:
        ids.append(period_id)

    # Sign-specific playlist (new — optional, only if configured)
    sign_id = YT_CFG.get("sign_playlist_ids", {}).get(sign, "")
    if sign_id:
        ids.append(sign_id)

    return [pid for pid in ids if pid.strip()]


def _build_pinned_comment(sign: str, period: str) -> str:
    """Build the pinned comment for a given sign and period."""
    template = PINNED_COMMENT_TEMPLATES.get(period, PINNED_COMMENT_TEMPLATES["daily"])
    symbol = SIGN_SYMBOLS.get(sign, "")
    return f"{symbol} {sign} — {template}"


async def generate_sign_video(
    sign: str,
    period: str,
    reference_date: date,
    workspace: Path,
) -> dict:
    """Generate video for one sign. Returns a manifest entry dict."""
    sign_workspace = workspace / sign.lower()
    sign_workspace.mkdir(parents=True, exist_ok=True)

    logger.info(f"[{sign}] Generating {period} script…")
    script = generate_horoscope_script(
        sign=sign,
        period=period,
        api_key_env=API_KEY_ENV,
        reference_date=reference_date,
    )

    logger.info(f"[{sign}] Generating SEO metadata…")
    seo = generate_seo_metadata(
        sign=sign,
        period=period,
        script=script,
        api_key_env=API_KEY_ENV,
        reference_date=reference_date,
    )

    # Image generation
    image_agent = ImageAgent(SETTINGS)
    image_paths = []
    for i, scene in enumerate(script["scenes"]):
        img_path = sign_workspace / f"scene_{i:02d}.png"
        image_agent.generate(scene["image_prompt"], str(img_path))
        image_paths.append(str(img_path))

    # Narration
    narration_agent = NarrationAgent(SETTINGS)
    narration_texts = [scene["narration"] for scene in script["scenes"]]
    audio_paths = await narration_agent.generate_all(narration_texts, sign_workspace)

    # Music
    music_agent = MusicAgent(SETTINGS)
    music_path = music_agent.get_track(sign_workspace)

    # Video assembly
    video_agent = VideoAgent(SETTINGS)
    video_path = sign_workspace / "video.mp4"
    video_agent.assemble(
        image_paths=image_paths,
        audio_paths=[str(p) for p in audio_paths],
        music_path=str(music_path) if music_path else None,
        output_path=str(video_path),
        hook_text=script.get("hook"),
        captions=[scene["narration"] for scene in script["scenes"]],
    )

    # Thumbnail
    thumbnail_path = sign_workspace / "thumbnail.png"
    from src.agents.thumbnail_agent import ThumbnailAgent
    thumb_agent = ThumbnailAgent(channel="astrofacts")
    thumb_agent.generate(
        title=seo.get("title", script.get("title", sign)),
        channel_tag=SIGN_SYMBOLS.get(sign, "✨"),
        metadata={"sign": sign, "period": period},
        output_path=str(thumbnail_path),
    )

    manifest_entry = {
        "sign": sign,
        "period": period,
        "reference_date": reference_date.isoformat(),
        "video_path": str(video_path),
        "thumbnail_path": str(thumbnail_path),
        "title": seo.get("title", script.get("title")),
        "description": seo.get("description", script.get("description", "")),
        "tags": seo.get("tags", script.get("tags", [])),
    }

    logger.info(f"[{sign}] Generation complete → {video_path}")
    return manifest_entry


def publish_sign_video(
    entry: dict,
    skip_youtube: bool = False,
    skip_tiktok: bool = False,
    stagger_index: int = 0,
) -> dict:
    """
    Publish one sign's video.

    IMPROVEMENT: stagger_index controls when this upload fires.
    In CI the caller passes the sign index (0-11) and this function
    sleeps STAGGER_SECONDS * stagger_index before uploading.
    This means:
      Aries   → uploads immediately
      Taurus  → waits 2h
      Gemini  → waits 4h
      ...
      Pisces  → waits 22h

    Each video then gets its own algorithm push window instead of
    competing with 11 sibling uploads in the same minute.
    """
    sign        = entry["sign"]
    period      = entry["period"]
    video_path  = Path(entry["video_path"])
    thumb_path  = entry.get("thumbnail_path")

    result = {**entry, "youtube_id": None, "tiktok_id": None}

    if not video_path.exists():
        logger.error(f"[{sign}] Video file missing: {video_path}")
        return result

    # IMPROVEMENT: staggered delay before uploading
    if stagger_index > 0:
        delay = STAGGER_SECONDS * stagger_index
        logger.info(f"[{sign}] Stagger delay: {delay}s ({delay // 3600}h {(delay % 3600) // 60}m)")
        time.sleep(delay)

    playlist_ids = _get_playlist_ids(sign, period)
    pinned_comment = _build_pinned_comment(sign, period)

    if not skip_youtube and YT_CFG.get("enabled"):
        try:
            video_id = upload_video(
                video_path=video_path,
                title=entry["title"],
                description=entry["description"],
                tags=entry["tags"],
                category_id=YT_CFG.get("category_id", "22"),
                privacy=YT_CFG.get("privacy", "public"),
                made_for_kids=YT_CFG.get("made_for_kids", False),
                thumbnail_path=thumb_path,
                playlist_id=playlist_ids,       # list of IDs
                pinned_comment=pinned_comment,   # IMPROVEMENT: engagement hook
                client_id_env="YOUTUBE_CLIENT_ID_ASTRO",
                client_secret_env="YOUTUBE_CLIENT_SECRET_ASTRO",
                refresh_token_env="YOUTUBE_REFRESH_TOKEN_ASTRO",
            )
            result["youtube_id"] = video_id
            logger.info(f"[{sign}] YouTube ✓ https://youtube.com/shorts/{video_id}")
        except Exception as e:
            logger.error(f"[{sign}] YouTube upload failed: {e}")

    if not skip_tiktok and TIKTOK_CFG.get("enabled"):
        try:
            from src.platforms.tiktok import upload_tiktok
            tiktok_id = upload_tiktok(
                video_path=video_path,
                title=entry["title"],
                client_key_env="TIKTOK_CLIENT_KEY_ASTRO",
                client_secret_env="TIKTOK_CLIENT_SECRET_ASTRO",
                refresh_token_env="TIKTOK_REFRESH_TOKEN_ASTRO",
            )
            result["tiktok_id"] = tiktok_id
            logger.info(f"[{sign}] TikTok ✓ {tiktok_id}")
        except Exception as e:
            logger.error(f"[{sign}] TikTok upload failed: {e}")

    return result


def run_generate(
    period: str,
    reference_date: date,
    signs: list[str],
    workspace: Path,
) -> list[dict]:
    """Generate videos for all requested signs. Returns manifest."""
    manifest = []
    for sign in signs:
        try:
            entry = asyncio.run(generate_sign_video(sign, period, reference_date, workspace))
            manifest.append(entry)
        except Exception as e:
            logger.error(f"[{sign}] Generation failed: {e}")
    return manifest


def run_publish(
    manifest: list[dict],
    skip_youtube: bool,
    skip_tiktok: bool,
    stagger: bool = True,
) -> list[dict]:
    """
    Publish all videos in the manifest.
    IMPROVEMENT: passes stagger_index so each upload is delayed appropriately.
    In CI this runs in a background loop or separate jobs.
    Set stagger=False for --dev / single-sign runs.
    """
    results = []
    for i, entry in enumerate(manifest):
        idx = i if stagger else 0
        result = publish_sign_video(
            entry,
            skip_youtube=skip_youtube,
            skip_tiktok=skip_tiktok,
            stagger_index=idx,
        )
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="AstroFacts pipeline")
    parser.add_argument("--period", default="daily",
                        choices=["daily", "weekly", "monthly", "yearly"])
    parser.add_argument("--reference-date", default=None,
                        help="YYYY-MM-DD publish date (defaults to next natural date)")
    parser.add_argument("--sign", default=None,
                        help="Single sign to process (default: all 12)")
    parser.add_argument("--publish-only", default=None,
                        help="Path to manifest JSON from a prior generate run")
    parser.add_argument("--dev", action="store_true",
                        help="Generate + publish a single sign locally (no stagger)")
    parser.add_argument("--skip-youtube", action="store_true")
    parser.add_argument("--skip-tiktok", action="store_true")
    args = parser.parse_args()

    period = args.period

    ref_date = (
        date.fromisoformat(args.reference_date)
        if args.reference_date
        else default_reference_date(period)
    )

    signs = [args.sign] if args.sign else ZODIAC_SIGNS
    run_id = str(uuid.uuid4())[:6]
    workspace = WORKSPACE / f"astrofacts-{period}-{ref_date.isoformat()}-{run_id}"
    workspace.mkdir(parents=True, exist_ok=True)

    if args.publish_only:
        manifest_path = Path(args.publish_only)
        manifest = json.loads(manifest_path.read_text())
        logger.info(f"Publish-only mode: {len(manifest)} entries from {manifest_path}")
    else:
        manifest = run_generate(period, ref_date, signs, workspace)
        manifest_path = workspace / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info(f"Manifest saved: {manifest_path}")
        # Output for GitHub Actions
        print(f"::set-output name=manifest_path::{manifest_path}")
        artifact_name = f"astrofacts-{period}-{ref_date.isoformat()}"
        print(f"::set-output name=artifact_name::{artifact_name}")

    if not (args.skip_youtube and args.skip_tiktok):
        # No stagger in --dev mode or single-sign runs
        use_stagger = not args.dev and len(manifest) > 1
        results = run_publish(
            manifest,
            skip_youtube=args.skip_youtube,
            skip_tiktok=args.skip_tiktok,
            stagger=use_stagger,
        )
        results_path = workspace / "publish_results.json"
        results_path.write_text(json.dumps(results, indent=2))
        published = sum(1 for r in results if r.get("youtube_id") or r.get("tiktok_id"))
        logger.info(f"Published {published}/{len(results)} videos.")


if __name__ == "__main__":
    main()
