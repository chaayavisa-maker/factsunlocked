"""
FactsUnlocked — Pipeline orchestrator
Generates a short-form video and publishes it to YouTube Shorts + TikTok.
"""

import os
import sys
import traceback
from pathlib import Path

from agents.topic_agent     import TopicAgent
from agents.script_agent    import ScriptAgent
from agents.image_agent     import ImageAgent
from agents.narration_agent import NarrationAgent
from agents.video_agent     import VideoAgent
from agents.seo_agent       import SEOAgent
from platforms.youtube      import upload_to_youtube
from platforms.tiktok       import upload_to_tiktok
from utils.logger           import get_logger

log = get_logger(__name__)


def run_pipeline() -> None:
    log.info("═══════════════════════════════════════")
    log.info("  FactsUnlocked pipeline starting")
    log.info("═══════════════════════════════════════")

    # 1. Research topic
    topic_agent = TopicAgent()
    topic       = topic_agent.get_trending_topic()
    log.info("Topic: %s", topic)

    # 2. Write script
    script_agent = ScriptAgent()
    script       = script_agent.write_script(topic)

    # 3. Generate images
    image_agent = ImageAgent()
    images      = image_agent.generate_images(script["scenes"])

    # 4. Generate narration
    narration_agent = NarrationAgent()
    audio_files     = narration_agent.generate_narration(script["scenes"])

    # 5. Assemble video
    video_agent = VideoAgent()
    video_path  = video_agent.assemble(script["scenes"], images, audio_files)
    log.info("Video assembled: %s", video_path)

    # 6. SEO metadata
    seo_agent = SEOAgent()
    metadata  = seo_agent.generate_metadata(topic, script)
    log.info("Title: %s", metadata["title"])

    # 7. Publish ─────────────────────────────────────────────────────────────
    errors = []

    # YouTube
    try:
        log.info("Uploading to YouTube…")
        youtube_url = upload_to_youtube(
            video_path  = video_path,
            title       = metadata["title"],
            description = metadata["description"],
            tags        = metadata["tags"],
        )
        log.info("✅ YouTube: %s", youtube_url)
    except Exception as exc:
        log.error("❌ YouTube upload failed: %s", exc)
        traceback.print_exc()
        errors.append(f"YouTube: {exc}")

    # TikTok
    try:
        log.info("Uploading to TikTok…")
        publish_id = upload_to_tiktok(
            video_path = video_path,
            title      = metadata["title"],   # used as caption
            privacy    = os.getenv("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"),
        )
        log.info("✅ TikTok publish_id: %s", publish_id)
    except Exception as exc:
        log.error("❌ TikTok upload failed: %s", exc)
        traceback.print_exc()
        errors.append(f"TikTok: {exc}")

    # ────────────────────────────────────────────────────────────────────────
    if errors:
        log.warning("Pipeline finished with errors:\n  %s", "\n  ".join(errors))
        # Exit 0 so GitHub Actions doesn't mark the run as failed
        # if only one platform failed (optional — change to sys.exit(1) if you prefer).
        sys.exit(0)

    log.info("═══════════════════════════════════════")
    log.info("  All done! 🎉")
    log.info("═══════════════════════════════════════")


if __name__ == "__main__":
    run_pipeline()
