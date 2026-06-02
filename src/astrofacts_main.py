"""
AstroFacts Pipeline Orchestrator
Uses the same class-based agents as FactsUnlocked, with AstroFacts settings.

Modes:
  default                        — generate all 12 signs, save manifest
  --publish-only <manifest_path> — publish from a previous generate run
  --sign <Sign>                  — single sign only (generate only, unless --dev)
  --dev --sign <Sign>            — generate + publish a single sign locally
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date
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
SETTINGS    = {                    # shape the original agents expect
    "channel": ASTRO_CFG["channel"],
    "video":   ASTRO_CFG["video"],
    "tts":     ASTRO_CFG["tts"],
}
API_KEY_ENV = ASTRO_CFG["groq_api_key_env"]   # "GROQ_API_KEY_ASTRO"
YT_CFG      = ASTRO_CFG["platforms"]["youtube"]
TIKTOK_CFG  = ASTRO_CFG["platforms"]["tiktok"]
WORKSPACE   = Path(CONFIG["video"]["workspace_dir"])


# ── GENERATE ─────────────────────────────────────────────────────────────────

async def generate_sign(sign: str, period: str) -> dict:
    """Full generation pipeline for one (sign, period). Does NOT publish."""
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

    # 1. Script (real planetary data injected inside)
    script = generate_horoscope_script(sign, period, api_key_env=API_KEY_ENV)

    # 2. SEO metadata
    seo = generate_seo_metadata(sign, period, script, api_key_env=API_KEY_ENV)

    # 3. Images — ImageAgent uses AstroFacts visual_style automatically
    image_paths = ImageAgent(SETTINGS).generate_all(script, ws)
    if not image_paths:
        raise RuntimeError(f"No images generated for {sign} {period}")

    # 4. Narration → (combined_audio, scene_durations)
    narration_path, scene_durations = await NarrationAgent(SETTINGS).generate(script, ws)

    # 5. Music
    music_path = MusicAgent(SETTINGS).get_track(ws)

    # 6. Video — VideoAgent reads watermark from SETTINGS["video"]["watermark"]
    hook_text = f"{symbol} {sign} {period.title()} Horoscope"
    final_path = VideoAgent(SETTINGS).assemble(
        workspace=str(ws),
        image_paths=image_paths,
        narration_path=str(narration_path),
        music_path=music_path,
        script=script,
        scene_durations=scene_durations,
        hook_text=hook_text,
    )

    music_credit = MusicAgent.get_credit() if music_path else ""
    metadata = {
        "run_id":      run_id,
        "sign":        sign,
        "period":      period,
        "title":       seo.get("title", script.get("title", f"{sign} {period.title()} Horoscope")),
        "description": seo.get("description", "") + (f"\n\n{music_credit}" if music_credit else ""),
        "tags":        seo.get("tags", []),
        "video_path":  final_path,
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata → {meta_path}")
    return metadata


async def generate_all_signs(period: str) -> list[dict]:
    logger.info(f"🔮 GENERATE — {period.upper()} batch for all 12 signs")
    results, errors = [], []

    for sign in ZODIAC_SIGNS:
        try:
            results.append(await generate_sign(sign, period))
        except Exception as e:
            logger.error(f"❌ Generate failed for {sign}: {e}", exc_info=True)
            errors.append(sign)

    manifest_path = WORKSPACE / f"manifest_{period}_{date.today().isoformat()}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(
        {"period": period, "runs": [r["run_id"] for r in results], "failed": errors},
        indent=2,
    ))
    logger.info(f"Manifest → {manifest_path}")
    logger.info(f"Generate complete — {len(results)}/12 succeeded")
    if errors:
        logger.error(f"Failed signs: {errors}")
    return results


# ── PUBLISH ──────────────────────────────────────────────────────────────────

def publish_sign(metadata: dict) -> dict:
    """Upload one sign's video to YouTube and/or TikTok."""
    sign      = metadata["sign"]
    period    = metadata["period"]
    video_path = Path(metadata["video_path"])

    logger.info("=" * 60)
    logger.info(f"  PUBLISH | {SIGN_SYMBOLS.get(sign,'✨')} {sign} | {period.upper()}")
    logger.info("=" * 60)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\n"
            "Make sure the generate artifact was downloaded first."
        )

    platform_ids = {}

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


def publish_from_manifest(manifest_path: Path, sign: str = None) -> None:
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
        metadata = json.loads(meta_path.read_text())
        # If --sign was given, only publish that one
        if sign and metadata.get("sign", "").lower() != sign.lower():
            continue
        try:
            publish_sign(metadata)
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
    parser.add_argument("--publish-only", metavar="MANIFEST_PATH", default=None)
    parser.add_argument("--dev", action="store_true", help="Generate + publish (local dev)")
    args = parser.parse_args()

    period = args.period
    sign   = args.sign.title() if args.sign else None

    if args.publish_only:
        publish_from_manifest(Path(args.publish_only), sign=sign)

    elif args.dev and sign:
        metadata = asyncio.run(generate_sign(sign, period))
        publish_sign(metadata)

    elif sign:
        asyncio.run(generate_sign(sign, period))

    else:
        asyncio.run(generate_all_signs(period))


if __name__ == "__main__":
    main()
