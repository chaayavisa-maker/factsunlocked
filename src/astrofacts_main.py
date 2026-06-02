"""
AstroFacts Pipeline Orchestrator
─────────────────────────────────
Two modes:

  GENERATE mode (default):
    Runs Groq → images → TTS → video render and saves
    workspace/<run_id>/final_video.mp4  +  metadata.json
    Does NOT publish.  Passes run_id to the publish job via
    the file  workspace/latest_run_id.txt  (uploaded as a
    GitHub Actions artifact).

  PUBLISH mode  (--publish-only <run_id>):
    Reads workspace/<run_id>/metadata.json and final_video.mp4
    that were downloaded from the GitHub artifact, then uploads
    to YouTube / TikTok.  No generation happens.

Usage:
    # Generate all 12 signs
    python src/astrofacts_main.py --period daily

    # Publish previously generated run
    python src/astrofacts_main.py --period daily --publish-only <run_id>

    # Single-sign test (generate + publish in one shot, for local dev)
    python src/astrofacts_main.py --period daily --sign Aries --dev
"""

import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.zodiac import ZODIAC_SIGNS, SIGN_SYMBOLS
from src.agents.horoscope_script_agent import generate_horoscope_script, generate_seo_metadata
from src.agents.image_agent import generate_scene_images
from src.agents.narration_agent import generate_scene_narrations
from src.agents.video_agent import build_video
from src.platforms.youtube import upload_video
from src.utils.logger import get_logger

logger = get_logger("astrofacts")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

ASTRO_CFG    = CONFIG["channels"]["astrofacts"]
VIDEO_CFG    = ASTRO_CFG["video"]
TTS_CFG      = ASTRO_CFG["tts"]
API_KEY_ENV  = ASTRO_CFG["groq_api_key_env"]   # "GROQ_API_KEY_ASTRO"
YT_CFG       = ASTRO_CFG["platforms"]["youtube"]
TIKTOK_CFG   = ASTRO_CFG["platforms"]["tiktok"]
WORKSPACE    = Path(CONFIG["video"]["workspace_dir"])


# ── GENERATE ─────────────────────────────────────────────────────────────────

def generate_sign(sign: str, period: str) -> dict:
    """
    Generate video for one sign.  Returns a metadata dict that includes the
    video path.  Does NOT publish.
    """
    run_id = (
        f"astrofacts_{period}_{sign.lower()}"
        f"_{date.today().isoformat()}_{uuid.uuid4().hex[:6]}"
    )
    ws = WORKSPACE / run_id
    ws.mkdir(parents=True, exist_ok=True)
    symbol = SIGN_SYMBOLS.get(sign, "✨")

    logger.info("=" * 60)
    logger.info(f"  GENERATE | {symbol} {sign} | {period.upper()} | {date.today()}")
    logger.info("=" * 60)

    # 1 – Script
    script = generate_horoscope_script(sign, period, api_key_env=API_KEY_ENV)
    scenes = script["scenes"]
    if script.get("hook"):
        scenes[0]["narration"] = script["hook"] + " " + scenes[0]["narration"]
    if script.get("closing_cta"):
        scenes[-1]["narration"] += " " + script["closing_cta"]

    # 2 – SEO
    seo   = generate_seo_metadata(sign, period, script, api_key_env=API_KEY_ENV)
    title = seo["title"]
    description = seo["description"]
    tags  = seo["tags"]

    # 3 – Images
    img_paths = generate_scene_images(
        scenes, ws / "images",
        width=VIDEO_CFG["resolution"][0],
        height=VIDEO_CFG["resolution"][1],
    )

    # 4 – Narration
    aud_paths = generate_scene_narrations(
        scenes, ws / "audio", voice=TTS_CFG["voice"]
    )

    # 5 – Video
    video_path = ws / "final_video.mp4"
    build_video(
        scenes=scenes,
        image_paths=img_paths,
        audio_paths=aud_paths,
        output_path=video_path,
        resolution=tuple(VIDEO_CFG["resolution"]),
        fps=VIDEO_CFG["fps"],
        font_size=VIDEO_CFG["font_size"],
        watermark=VIDEO_CFG.get("watermark"),
        hook_text=f"{symbol} {sign} {period.title()} Horoscope",
    )

    # 6 – Persist metadata so publish job can read it without regenerating
    metadata = {
        "run_id":      run_id,
        "sign":        sign,
        "period":      period,
        "title":       title,
        "description": description,
        "tags":        tags,
        "video_path":  str(video_path),
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata written → {meta_path}")

    return metadata


def generate_all_signs(period: str) -> list[dict]:
    logger.info(f"🔮 GENERATE — {period.upper()} batch for all 12 signs")
    results, errors = [], []

    for sign in ZODIAC_SIGNS:
        try:
            results.append(generate_sign(sign, period))
        except Exception as e:
            logger.error(f"❌ Generate failed for {sign}: {e}", exc_info=True)
            errors.append(sign)

    # Write a manifest so the publish job knows which run_ids to download
    manifest_path = WORKSPACE / f"manifest_{period}_{date.today().isoformat()}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(
        {"period": period, "runs": [r["run_id"] for r in results], "failed": errors},
        indent=2,
    ))
    logger.info(f"Manifest → {manifest_path}")

    logger.info(f"\nGenerate complete — {len(results)}/12 succeeded")
    if errors:
        logger.error(f"Failed signs: {errors}")
    return results


# ── PUBLISH ──────────────────────────────────────────────────────────────────

def publish_sign(metadata: dict) -> dict:
    """
    Publish one sign's video to YouTube and/or TikTok.
    Reads pre-rendered video from metadata['video_path'].
    """
    sign    = metadata["sign"]
    period  = metadata["period"]
    video_path = Path(metadata["video_path"])

    logger.info("=" * 60)
    logger.info(f"  PUBLISH | {SIGN_SYMBOLS.get(sign,'✨')} {sign} | {period.upper()}")
    logger.info("=" * 60)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found at {video_path}. "
            "Make sure the generate artifact was downloaded before this job."
        )

    platform_ids = {}

    # YouTube
    if YT_CFG.get("enabled"):
        playlist_id = YT_CFG.get("playlist_ids", {}).get(period)
        yt_id = upload_video(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            category_id=YT_CFG.get("category_id", "22"),
            privacy=YT_CFG.get("privacy", "public"),
            made_for_kids=YT_CFG.get("made_for_kids", False),
            playlist_id=playlist_id,
            client_id_env="YOUTUBE_CLIENT_ID_ASTRO",
            client_secret_env="YOUTUBE_CLIENT_SECRET_ASTRO",
            refresh_token_env="YOUTUBE_REFRESH_TOKEN_ASTRO",
        )
        platform_ids["youtube"] = yt_id
        logger.info(f"YouTube ✅ https://youtube.com/shorts/{yt_id}")

    # TikTok
    if TIKTOK_CFG.get("enabled"):
        from src.platforms.tiktok import upload_video_tiktok
        tt_id = upload_video_tiktok(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
        )
        platform_ids["tiktok"] = tt_id
        logger.info(f"TikTok ✅ publish_id={tt_id}")

    logger.info(f"✅ Published {sign} {period}: {platform_ids}")
    return {**metadata, "platform_ids": platform_ids}


def publish_from_manifest(manifest_path: Path) -> None:
    """Publish all signs listed in a manifest JSON (used by the publish job)."""
    manifest = json.loads(manifest_path.read_text())
    period   = manifest["period"]
    run_ids  = manifest["runs"]

    logger.info(f"🚀 PUBLISH — {period.upper()} from manifest ({len(run_ids)} runs)")
    errors = []

    for run_id in run_ids:
        meta_path = WORKSPACE / run_id / "metadata.json"
        if not meta_path.exists():
            logger.error(f"metadata.json missing for run_id={run_id} — skipping")
            errors.append(run_id)
            continue
        try:
            metadata = json.loads(meta_path.read_text())
            publish_sign(metadata)
        except Exception as e:
            logger.error(f"❌ Publish failed for run_id={run_id}: {e}", exc_info=True)
            errors.append(run_id)

    logger.info(f"\nPublish complete — {len(run_ids)-len(errors)}/{len(run_ids)} succeeded")
    if errors:
        logger.error(f"Failed run_ids: {errors}")
        sys.exit(1)


# ── LOCAL DEV: single-sign generate + publish in one shot ────────────────────

def dev_run(sign: str, period: str) -> None:
    metadata = generate_sign(sign, period)
    publish_sign(metadata)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AstroFacts pipeline")
    parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly", "yearly"],
        required=True,
    )
    parser.add_argument(
        "--sign",
        choices=ZODIAC_SIGNS + [s.lower() for s in ZODIAC_SIGNS],
        default=None,
        help="Single sign (for testing / manual reruns)",
    )
    parser.add_argument(
        "--publish-only",
        metavar="MANIFEST_PATH",
        default=None,
        help="Path to manifest JSON from a previous generate run. "
             "Skips generation entirely and only publishes.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Generate AND publish in a single process (local dev only)",
    )
    args = parser.parse_args()
    period = args.period
    sign   = args.sign.title() if args.sign else None

    if args.publish_only:
        # ── Publish-only mode (re-run of failed publish job) ─────────────────
        manifest_path = Path(args.publish_only)
        if sign:
            # Re-publish a single sign from a known run workspace
            meta_path = manifest_path / "metadata.json" if manifest_path.is_dir() else manifest_path
            metadata  = json.loads(meta_path.read_text())
            publish_sign(metadata)
        else:
            publish_from_manifest(manifest_path)

    elif args.dev and sign:
        # ── Local dev: one sign, full pipeline ───────────────────────────────
        dev_run(sign, period)

    elif sign:
        # ── Generate only, single sign (e.g. manual re-generate) ─────────────
        generate_sign(sign, period)

    else:
        # ── Normal CI: generate all 12 (publish handled by separate job) ─────
        generate_all_signs(period)


if __name__ == "__main__":
    main()
