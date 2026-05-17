import asyncio
import os
import uuid
from pathlib import Path

import yaml

from agents.topic_agent import TopicAgent
from agents.script_agent import ScriptAgent
from agents.image_agent import ImageAgent
from agents.narration_agent import NarrationAgent
from agents.music_agent import MusicAgent, MUSIC_CREDIT
from agents.video_agent import VideoAgent
from agents.seo_agent import SEOAgent
from platforms.youtube import YouTubePublisher
from utils.logger import get_logger

logger = get_logger(__name__)


def load_settings() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


async def run_pipeline():
    settings = load_settings()
    run_id = str(uuid.uuid4())[:8]
    workspace = Path(f"workspace/{run_id}")
    workspace.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== Pipeline run {run_id} ===")

    # 1. Topic
    topic_agent = TopicAgent(settings)
    topic = topic_agent.get_topic()
    logger.info(f"Topic: {topic}")

    # 2. Script (hook formula)
    script_agent = ScriptAgent(settings)
    script = script_agent.generate(topic)
    logger.info(f"Hook: {script['hook']}")
    logger.info(f"Title: {script['title']}")

    # 3. Images (consistent cinematic style)
    image_agent = ImageAgent(settings)
    image_paths = image_agent.generate_all(script, workspace)
    logger.info(f"Images: {len(image_paths)} generated")

    if not image_paths:
        raise RuntimeError("No images generated — aborting.")

    # 4. Narration
    narration_agent = NarrationAgent(settings)
    narration_path = await narration_agent.generate(script, workspace)
    logger.info(f"Narration: {narration_path}")

    # 5. Background music (free, CC-BY, no API key)
    music_agent = MusicAgent(settings)
    music_path = music_agent.get_track(workspace)
    logger.info(f"Music: {music_path or 'unavailable'}")

    # 6. Video assembly (Ken Burns + captions + music)
    video_agent = VideoAgent(settings)
    video_path = video_agent.assemble(
        str(workspace),
        image_paths,
        narration_path,
        music_path,
        script,
    )
    logger.info(f"Video: {video_path}")

    # 7. SEO metadata (include CC-BY music credit in description)
    seo_agent = SEOAgent(settings)
    metadata = seo_agent.generate(topic, script, extra_description=MUSIC_CREDIT)
    logger.info(f"Title: {metadata['title']}")

    # 8. Upload
    publisher = YouTubePublisher()
    video_id = publisher.upload(video_path, metadata)
    logger.info(f"Published: https://youtube.com/shorts/{video_id}")

    return video_id


if __name__ == "__main__":
    asyncio.run(run_pipeline())
