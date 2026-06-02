"""
FactsUnlocked Pipeline Orchestrator
─────────────────────────────────────
GENERATE mode (default):
    Groq topic → script → images → TTS → video.
    Saves workspace/<run_id>/final_video.mp4  +  metadata.json.
    Does NOT publish.

PUBLISH mode (--publish-only <metadata_path>):
    Reads an existing metadata.json and uploads the video.
    No generation happens — safe to re-run after a publish failure.

DEV mode (--dev):
    Generate + publish in one shot (local testing only).
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.image_agent import generate_scene_images
from src.agents.narration_agent import generate_scene_narrations
from src.agents.video_agent import build_video
from src.platforms.youtube import upload_video
from src.utils.groq_client import call_groq
from src.utils.logger import get_logger

logger = get_logger("factsunlocked")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

FU_CFG       = CONFIG["channels"]["factsunlocked"]
VIDEO_CFG    = FU_CFG["video"]
TTS_CFG      = FU_CFG["tts"]
API_KEY_ENV  = FU_CFG["groq_api_key_env"]   # "GROQ_API_KEY"
YT_CFG       = FU_CFG["platforms"]["youtube"]
WORKSPACE    = Path(CONFIG["video"]["workspace_dir"])


# ── Groq helpers ─────────────────────────────────────────────────────────────

def research_topic() -> str:
    return call_groq(
        "Give me one fascinating, little-known fact about science, history, "
        "nature, or technology that would work perfectly for a 60-second YouTube "
        "Short. Return only the topic title, nothing else.",
        api_key_env=API_KEY_ENV,
    )


def write_script(topic: str) -> dict:
    system = "You are an expert YouTube Shorts scriptwriter. Return ONLY valid JSON."
    prompt = f"""Write a YouTube Shorts script about: {topic}

Return JSON:
{{
  "title": "catchy title ≤60 chars",
  "scenes": [
    {{
      "narration": "15-second narration",
      "image_prompt": "detailed image generation prompt, portrait, no text"
    }}
  ],
  "description": "YouTube description 150-200 chars",
  "tags": ["8 seo tags"]
}}

Exactly {VIDEO_CFG['scenes_count']} scenes."""

    raw = call_groq(prompt, system=system, max_tokens=1200, api_key_env=API_KEY_ENV)
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


# ── GENERATE ─────────────────────────────────────────────────────────────────

def generate() -> dict:
    run_id = f"factsunlocked_{date.today().isoformat()}_{uuid.uuid4().hex[:6]}"
    ws = WORKSPACE / run_id
    ws.mkdir(parents=True, exist_ok=True)

    logger.info("🔬 FactsUnlocked — GENERATE")

    topic  = research_topic()
    logger.info(f"Topic: {topic}")

    script = write_script(topic)
    scenes = script["scenes"]

    img_paths = generate_scene_images(
        scenes, ws / "images",
        width=VIDEO_CFG["resolution"][0],
        height=VIDEO_CFG["resolution"][1],
    )
    aud_paths = generate_scene_narrations(
        scenes, ws / "audio", voice=TTS_CFG["voice"]
    )
    video_path = ws / "final_video.mp4"
    build_video(
        scenes=scenes,
        image_paths=img_paths,
        audio_paths=aud_paths,
        output_path=video_path,
        resolution=tuple(VIDEO_CFG["resolution"]),
        fps=VIDEO_CFG["fps"],
        font_size=VIDEO_CFG["font_size"],
    )

    metadata = {
        "run_id":      run_id,
        "title":       script["title"],
        "description": script["description"],
        "tags":        script.get("tags", []),
        "video_path":  str(video_path),
    }
    meta_path = ws / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    logger.info(f"Metadata → {meta_path}")
    return metadata


# ── PUBLISH ──────────────────────────────────────────────────────────────────

def publish(metadata: dict) -> str:
    video_path = Path(metadata["video_path"])
    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}\n"
            "Ensure the generate artifact was downloaded before running publish."
        )

    logger.info("📤 FactsUnlocked — PUBLISH")

    yt_id = upload_video(
        video_path=video_path,
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
        category_id=YT_CFG.get("category_id", "28"),
        privacy=YT_CFG.get("privacy", "public"),
        made_for_kids=YT_CFG.get("made_for_kids", False),
    )
    logger.info(f"✅ Published: https://youtube.com/shorts/{yt_id}")
    return yt_id


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FactsUnlocked pipeline")
    parser.add_argument(
        "--publish-only",
        metavar="METADATA_PATH",
        default=None,
        help="Path to metadata.json from a previous generate run. "
             "Skips generation and only publishes.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Generate AND publish in one shot (local dev only)",
    )
    args = parser.parse_args()

    if args.publish_only:
        meta_path = Path(args.publish_only)
        metadata  = json.loads(meta_path.read_text())
        publish(metadata)
    elif args.dev:
        metadata = generate()
        publish(metadata)
    else:
        generate()


if __name__ == "__main__":
    main()
