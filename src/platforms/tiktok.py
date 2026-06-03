"""
TikTokPublisher – uploads videos to TikTok via the TikTok Content Posting API.

Prerequisites
─────────────
1. Apply for TikTok for Developers access at https://developers.tiktok.com
2. Create an app and enable "Content Posting API"
3. Complete OAuth flow once using scripts/get_tiktok_token.py
4. Store the refresh token in GitHub secret TIKTOK_REFRESH_TOKEN_ASTRO

Reference: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

import os
import json
import time
import httpx
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)

TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _refresh_access_token(
    client_key_env: str = "TIKTOK_CLIENT_KEY_ASTRO",
    client_secret_env: str = "TIKTOK_CLIENT_SECRET_ASTRO",
    refresh_token_env: str = "TIKTOK_REFRESH_TOKEN_ASTRO",
) -> str:
    """Exchange refresh token for a new access token."""
    payload = {
        "client_key": os.environ[client_key_env],
        "client_secret": os.environ[client_secret_env],
        "grant_type": "refresh_token",
        "refresh_token": os.environ[refresh_token_env],
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(TIKTOK_TOKEN_URL, data=payload)
        resp.raise_for_status()
    data = resp.json()
    token_data = data.get("data") or data
    if "access_token" not in token_data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    return token_data["access_token"]


def upload_video_tiktok(
    video_path: Path,
    title: str,
    description: str = "",
    max_duration_seconds: int = 60,
    privacy_level: str = "SELF_ONLY",
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
    client_key_env: str = "TIKTOK_CLIENT_KEY_ASTRO",
    client_secret_env: str = "TIKTOK_CLIENT_SECRET_ASTRO",
    refresh_token_env: str = "TIKTOK_REFRESH_TOKEN_ASTRO",
) -> str:
    """
    Upload a video to TikTok using the Content Posting API.
    Returns the TikTok publish_id.
    """
    access_token = _refresh_access_token(
        client_key_env, client_secret_env, refresh_token_env
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    video_size = video_path.stat().st_size
    chunk_size = min(video_size, 10 * 1024 * 1024)  # 10MB max chunk

    # Caption: TikTok allows 2200 chars; combine title + description
    caption = f"{title}\n\n{description}"[:2200]

    # Step 1: Initialise upload
    init_body = {
        "post_info": {
            "title": caption,
            "privacy_level": privacy_level,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": -(-video_size // chunk_size),  # ceiling div
        },
    }

    logger.info(f"Initialising TikTok upload for '{title}'…")
    with httpx.Client(timeout=30) as client:
        resp = client.post(TIKTOK_INIT_URL, headers=headers, json=init_body)
        resp.raise_for_status()

    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok init failed: {data}")

    upload_url = data["data"]["upload_url"]
    publish_id = data["data"]["publish_id"]

    # Step 2: Upload chunks
    logger.info(f"Uploading video chunks to TikTok…")
    video_bytes = video_path.read_bytes()
    chunks = [video_bytes[i:i+chunk_size] for i in range(0, video_size, chunk_size)]

    for idx, chunk in enumerate(chunks):
        start = idx * chunk_size
        end = start + len(chunk) - 1
        chunk_headers = {
            "Content-Range": f"bytes {start}-{end}/{video_size}",
            "Content-Type": "video/mp4",
        }
        with httpx.Client(timeout=120) as client:
            put_resp = client.put(upload_url, headers=chunk_headers, content=chunk)
            put_resp.raise_for_status()
        logger.info(f"Chunk {idx+1}/{len(chunks)} uploaded.")

    # Step 3: Poll status
    logger.info("Polling TikTok publish status…")
    for _ in range(20):
        time.sleep(10)
        status_body = {"publish_id": publish_id}
        with httpx.Client(timeout=30) as client:
            st_resp = client.post(TIKTOK_STATUS_URL, headers=headers, json=status_body)
            st_resp.raise_for_status()
        st_data = st_resp.json()
        status = st_data.get("data", {}).get("status", "")
        logger.info(f"TikTok status: {status}")
        if status == "PUBLISH_COMPLETE":
            logger.info(f"TikTok publish complete! publish_id={publish_id}")
            return publish_id
        if status in ("FAILED", "PUBLISH_FAILED"):
            raise RuntimeError(f"TikTok publish failed: {st_data}")

    logger.warning("TikTok status polling timed out — video may still be processing.")
    return publish_id
