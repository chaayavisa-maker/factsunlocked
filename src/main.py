import asyncio
import json
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


# ---------------------------------------------------------------------------
# Pipeline state — persists step results to JSON so runs are resumable
# ---------------------------------------------------------------------------

class PipelineState:
    """
    Writes pipeline_state.json inside the workspace after every step.
    On re-run with the same PIPELINE_RUN_ID the completed steps are skipped.
    """

    def __init__(self, workspace: Path):
        self.path = workspace / "pipeline_state.json"
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception as exc:
                logger.warning(f"Could not read state file ({exc}) — starting fresh.")
        return {"steps": {}}

    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2, default=str))

    def is_done(self, step: str) -> bool:
        return self._data["steps"].get(step, {}).get("status") == "done"

    def result(self, step: str):
        return self._data["steps"].get(step, {}).get("output")

    def mark_done(self, step: str, output=None):
        self._data["steps"][step] = {"status": "done", "output": output}
        self._save()

    def reset_step(self, step: str):
        self._data["steps"].pop(step, None)
        self._save()


def _file_ok(path) -> bool:
    return bool(path) and Path(str(path)).exists()


def _skip(step: str, value):
    logger.info(f"  ⏭  [{step}] already complete — skipping.")
    return value


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


async def run_pipeline():
    settings = load_settings()

    run_id = os.environ.get("PIPELINE_RUN_ID") or str(uuid.uuid4())[:8]
    workspace = Path(f"workspace/{run_id}")
    workspace.mkdir(parents=True, exist_ok=True)

    state = PipelineState(workspace)

    logger.info("=" * 60)
    logger.info(f"Pipeline run_id : {run_id}")
    logger.info(f"Workspace       : {workspace}")
    logger.info(f"To resume: set PIPELINE_RUN_ID={run_id}")
    logger.info("=" * 60)

    # ── Step 1: Topic ──────────────────────────────────────────────────────
    STEP = "topic"
    if state.is_done(STEP):
        topic = _skip(STEP, state.result(STEP))
    else:
        topic = TopicAgent().get_topic()
        state.mark_done(STEP, topic)
        logger.info(f"  ✓ [{STEP}] {topic}")

    # ── Step 2: Script ─────────────────────────────────────────────────────
    STEP = "script"
    if state.is_done(STEP):
        script = _skip(STEP, state.result(STEP))
    else:
        script = ScriptAgent(settings).generate(topic)
        state.mark_done(STEP, script)
        logger.info(f"  ✓ [{STEP}] hook='{script['hook']}'  title='{script['title']}'")

    # ── Step 3: Images ─────────────────────────────────────────────────────
    STEP = "images"
    if state.is_done(STEP):
        image_paths = state.result(STEP) or []
        missing = [p for p in image_paths if not _file_ok(p)]
        if missing:
            logger.warning(
                f"  ⚠  [{STEP}] {len(missing)} image file(s) missing — regenerating."
            )
            state.reset_step(STEP)
        else:
            _skip(STEP, image_paths)

    if not state.is_done(STEP):
        image_paths = ImageAgent(settings).generate_all(script, workspace)
        if not image_paths:
            raise RuntimeError("No images generated — aborting.")
        state.mark_done(STEP, image_paths)
        logger.info(f"  ✓ [{STEP}] {len(image_paths)} images generated.")

    # ── Step 4: Narration ──────────────────────────────────────────────────
    # Returns (combined_mp3_path, per_scene_durations)
    STEP = "narration"
    if state.is_done(STEP):
        saved = state.result(STEP)
        narration_path = saved["path"] if isinstance(saved, dict) else saved
        scene_durations = saved.get("durations") if isinstance(saved, dict) else None
        if not _file_ok(narration_path):
            logger.warning(f"  ⚠  [{STEP}] file missing — regenerating.")
            state.reset_step(STEP)
        else:
            _skip(STEP, saved)

    if not state.is_done(STEP):
        narration_path, scene_durations = await NarrationAgent(settings).generate(
            script, workspace
        )
        narration_path = str(narration_path)
        state.mark_done(STEP, {"path": narration_path, "durations": scene_durations})
        logger.info(
            f"  ✓ [{STEP}] {narration_path} "
            f"(scenes: {[f'{d:.1f}s' for d in scene_durations]})"
        )

    # ── Step 5: Music ──────────────────────────────────────────────────────
    STEP = "music"
    if state.is_done(STEP):
        music_path = state.result(STEP)
        if music_path and not _file_ok(music_path):
            logger.warning(f"  ⚠  [{STEP}] file missing — re-downloading.")
            state.reset_step(STEP)
        else:
            _skip(STEP, music_path)

    if not state.is_done(STEP):
        music_path = MusicAgent(settings).get_track(workspace)
        state.mark_done(STEP, str(music_path) if music_path else None)
        logger.info(f"  ✓ [{STEP}] {music_path or 'unavailable'}")

    # ── Step 6: Video assembly ─────────────────────────────────────────────
    STEP = "video"
    if state.is_done(STEP):
        video_path = state.result(STEP)
        if not _file_ok(video_path):
            logger.warning(f"  ⚠  [{STEP}] file missing — re-rendering.")
            state.reset_step(STEP)
        else:
            _skip(STEP, video_path)

    if not state.is_done(STEP):
        video_path = VideoAgent(settings).assemble(
            str(workspace),
            image_paths,
            narration_path,
            music_path,
            script,
            scene_durations=scene_durations,   # ← per-scene timing
        )
        state.mark_done(STEP, str(video_path))
        logger.info(f"  ✓ [{STEP}] {video_path}")

    # ── Step 7: SEO metadata ───────────────────────────────────────────────
    STEP = "seo"
    if state.is_done(STEP):
        metadata = _skip(STEP, state.result(STEP))
    else:
        metadata = SEOAgent().generate(topic, script, extra_description=MUSIC_CREDIT)
        state.mark_done(STEP, metadata)
        logger.info(f"  ✓ [{STEP}] title='{metadata['title']}'")

    # ── Step 8: Upload ─────────────────────────────────────────────────────
    STEP = "upload"
    if state.is_done(STEP):
        video_id = _skip(STEP, state.result(STEP))
    else:
        if os.environ.get("DRY_RUN", "false").lower() == "true":
            video_id = "DRY_RUN"
            logger.info(f"  ✓ [{STEP}] DRY_RUN — upload skipped.")
        else:
            publisher = YouTubePublisher()
            video_id = publisher.upload(Path(video_path), metadata)
            logger.info(f"  ✓ [{STEP}] https://youtube.com/shorts/{video_id}")
        state.mark_done(STEP, video_id)

    logger.info("=" * 60)
    logger.info(f"Pipeline complete  run_id={run_id}  video_id={video_id}")
    logger.info("=" * 60)
    return video_id


if __name__ == "__main__":
    asyncio.run(run_pipeline())
