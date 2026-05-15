import asyncio
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Make sure src/ is on the path when run from repo root
sys.path.insert(0, str(Path(__file__).parent))

from agents.topic_agent import TopicAgent
from agents.script_agent import ScriptAgent
from agents.image_agent import ImageAgent
from agents.narration_agent import NarrationAgent
from agents.video_agent import VideoAgent
from agents.seo_agent import SEOAgent
from platforms.youtube import YouTubePublisher
from utils.logger import setup_logger

logger = setup_logger("pipeline")


def _save_run_log(workspace: Path, data: dict) -> None:
    log_path = workspace / "run_log.json"
    with open(log_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Run log saved: {log_path}")


async def run_pipeline() -> dict:
    """
    Full autonomous pipeline:
      1. Research trending topic
      2. Write 6-scene script
      3. Generate scene images  (Pollinations.ai — free)
      4. Generate TTS narration (edge-tts — free)
      5. Assemble MP4          (moviepy + ffmpeg)
      6. Generate SEO metadata (Groq — free)
      7. Upload to YouTube     (YouTube Data API v3)
    Returns result dict with video_id and public URL.
    """
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    workspace = Path("workspace") / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    logger.info(f"=== Pipeline run {run_id} started ===")

    result = {"run_id": run_id, "status": "started", "workspace": str(workspace)}

    try:
        # ── Step 1: Topic ──────────────────────────────────────────────────
        logger.info("▶ Step 1/7 — Topic research")
        topic_agent = TopicAgent()
        topic = topic_agent.generate_video_topic()
        result["topic"] = topic["title"]
        logger.info(f"   Topic: {topic['title']}")

        # ── Step 2: Script ─────────────────────────────────────────────────
        logger.info("▶ Step 2/7 — Script writing")
        script_agent = ScriptAgent()
        script = script_agent.write_script(topic)
        result["scenes"] = len(script["scenes"])
        logger.info(f"   Script: {result['scenes']} scenes")

        # ── Step 3: Images ─────────────────────────────────────────────────
        logger.info("▶ Step 3/7 — Image generation")
        image_agent = ImageAgent()
        images = await image_agent.generate_all_images(script, workspace)
        result["images_generated"] = len(images)

        # ── Step 4: Narration ──────────────────────────────────────────────
        logger.info("▶ Step 4/7 — TTS narration")
        narration_agent = NarrationAgent()
        audio_files = await narration_agent.generate_all_narration(script, workspace)
        result["audio_clips"] = len(audio_files)

        # ── Step 5: Video assembly ─────────────────────────────────────────
        logger.info("▶ Step 5/7 — Video assembly")
        video_agent = VideoAgent()
        video_path = video_agent.assemble_video(script, images, audio_files, workspace)
        result["video_path"] = str(video_path)
        result["video_size_mb"] = round(video_path.stat().st_size / (1024 * 1024), 1)

        # ── Step 6: SEO ────────────────────────────────────────────────────
        logger.info("▶ Step 6/7 — SEO metadata")
        seo_agent = SEOAgent()
        metadata = seo_agent.generate_metadata(topic, script)
        result["youtube_title"] = metadata["title"]

        # ── Step 7: Publish ────────────────────────────────────────────────
        logger.info("▶ Step 7/7 — YouTube upload")
        publisher = YouTubePublisher()
        video_id = publisher.upload(video_path, metadata)

        # Optional thumbnail (first scene image)
        publisher.set_thumbnail(video_id, images[0])

        result["video_id"] = video_id
        result["url"] = f"https://www.youtube.com/shorts/{video_id}"
        result["status"] = "published"

        logger.info(f"=== ✅ DONE — {result['url']} ===")

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        logger.error(f"Pipeline failed: {exc}", exc_info=True)
        raise

    finally:
        _save_run_log(workspace, result)
        # Keep workspace for debugging; GitHub Actions will discard it anyway
        logger.info(f"Workspace: {workspace}")

    return result


if __name__ == "__main__":
    asyncio.run(run_pipeline())
