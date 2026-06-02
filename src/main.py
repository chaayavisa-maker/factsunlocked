"""
FactsUnlocked Pipeline Orchestrator

Modes:
  default        — full pipeline: generate + publish (YouTube + TikTok)
  --publish-only — skip generation, upload existing metadata.json
  --dev          — generate + publish in one shot (local testing)
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.image_agent     import ImageAgent
from src.agents.narration_agent import NarrationAgent
from src.agents.video_agent     import VideoAgent
from src.agents.music_agent     import MusicAgent
from src.agents.topic_agent     import TopicAgent
from src.agents.script_agent    import ScriptAgent
from src.agents.seo_agent       import SEOAgent
from src.platforms.youtube      import upload_video
from src.utils.logger           import get_logger

logger = get_logger("factsunlocked")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

FU_CFG    = CONFIG["channels"]["factsunlocked"]
SETTINGS  = {
    "channel": FU_CFG["channel"],
    "video":   FU_CFG["video"],
    "tts":     FU_CFG["tts"],
}
YT_CFG     = FU_CFG["platforms"]["youtube"]
TIKTOK_CFG = FU_CFG["platforms"]["tiktok"]
WORKSPACE  = Path(CONFIG["video"]["workspace_dir"])


# ── GENERATE ─────────────────────────────────────────────────────────────────

async def generate() -> dict:
    import uuid
    run_id = f"factsunlocked_{date.today().isoformat()}_{uuid.uuid4().hex[:6]}"
    ws = WORKSPACE / run_id
    ws.mkdir(parents=True, exist_ok=True)

    logger.info("🔬 FactsUnlocked — GENERATE")

    # 1. Topic
    topic = TopicAgent().get_topic()
    logger.info(f"Topic: {topic}")

    # 2. Script
    script = ScriptAgent(SETTINGS).generate(topic)

    # 3. Images
    image_paths = ImageAgent(SETTINGS).generate_all(script, ws)
    if not image_paths:
        raise RuntimeError("No images were generated — aborting.")

    # 4. Narration → (combined_audio_path, per_scene_durations)
    narration_path, scene_durations = await NarrationAgent(SETTINGS).generate(script, ws)

    # 5. Music
    music_path = MusicAgent(SETTINGS).get_track(ws)

    # 6. Video
    final_path = VideoAgent(SETTINGS).assemble(
        workspace=str(ws),
        image_paths=image_paths,
        narration_path=str(narration_path),
        music_path=music_path,
        script=script,
        scene_durations=scene_durations,
    )

    # 7. SEO metadata
    seo = SEOAgent().generate(topic, script)
    music_credit = MusicAgent.get_credit() if music_path else ""

    metadata = {
        "run_id":      run_id,
        "title":       seo.get("title", script.get("title", topic)),
        "description": seo.get("description", "") + (f"\n\n{music_credit}" if music_credit else ""),
        "tags":        seo.get("tags", []),
        "video_path":  final_path,
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata → {meta_path}")
    return metadata


# ── PUBLISH ──────────────────────────────────────────────────────────────────

def publish(metadata: dict) -> dict:
    video_path = Path(metadata["video_path"])
    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\n"
            "Make sure the generate artifact was downloaded before running publish."
        )

    logger.info("📤 FactsUnlocked — PUBLISH")
    platform_ids = {}

    # ── YouTube ──────────────────────────────────────────────────────────────
    if YT_CFG.get("enabled"):
        yt_id = upload_video(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            category_id=YT_CFG.get("category_id", "28"),
            privacy=YT_CFG.get("privacy", "public"),
            made_for_kids=YT_CFG.get("made_for_kids", False),
        )
        platform_ids["youtube"] = yt_id
        logger.info(f"YouTube ✅ https://youtube.com/shorts/{yt_id}")

    # ── TikTok ───────────────────────────────────────────────────────────────
    if TIKTOK_CFG.get("enabled"):
        from src.platforms.tiktok import upload_video_tiktok
        tt_id = upload_video_tiktok(
            video_path=video_path,
            title=metadata["title"],
            description=metadata["description"],
            client_key_env="TIKTOK_CLIENT_KEY",
            client_secret_env="TIKTOK_CLIENT_SECRET",
            refresh_token_env="TIKTOK_REFRESH_TOKEN",
        )
        platform_ids["tiktok"] = tt_id
        logger.info(f"TikTok ✅ publish_id={tt_id}")

    logger.info(f"✅ Published FactsUnlocked: {platform_ids}")
    return {**metadata, "platform_ids": platform_ids}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FactsUnlocked pipeline")
    parser.add_argument("--publish-only", metavar="METADATA_PATH", default=None)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    if args.publish_only:
        metadata = json.loads(Path(args.publish_only).read_text())
        publish(metadata)
    elif args.dev:
        metadata = asyncio.run(generate())
        publish(metadata)
    else:
        metadata = asyncio.run(generate())
        publish(metadata)


if __name__ == "__main__":
    main()
