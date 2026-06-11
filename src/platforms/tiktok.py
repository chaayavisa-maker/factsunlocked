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
import math
import time
import httpx
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)

TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# TikTok FILE_UPLOAD chunk constraints
_MIN_CHUNK = 5 * 1024 * 1024   # 5 MB  – TikTok's documented minimum
_MAX_CHUNK = 64 * 1024 * 1024  # 64 MB – TikTok's documented maximum


def _refresh_access_token(
    client_key_env: str = "TIKTOK_CLIENT_KEY_ASTRO",
    client_secret_env: str = "TIKTOK_CLIENT_SECRET_ASTRO",
    refresh_token_env: str = "TIKTOK_REFRESH_TOKEN_ASTRO",
) -> str:
    payload = {
        "client_key": os.environ[client_key_env],
        "client_secret": os.environ[client_secret_env],
        "grant_type": "refresh_token",
        "refresh_token": os.environ[refresh_token_env],
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(TIKTOK_TOKEN_URL, data=payload)
        logger.info(f"Token refresh status: {resp.status_code}")
        logger.info(f"Token refresh response: {resp.text}")
        resp.raise_for_status()
    data = resp.json()
    token_data = data.get("data") or data
    if "access_token" not in token_data:
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    return token_data["access_token"]


def _compute_chunks(video_size: int) -> tuple[int, int]:
    """
    Return (chunk_size, total_chunk_count) for a given video_size.

    TikTok rules
    ────────────
    • chunk_size must be between _MIN_CHUNK and _MAX_CHUNK …
    • … EXCEPT when total_chunk_count == 1, chunk_size may equal video_size
      (even if video_size < _MIN_CHUNK).
    • The last chunk of a multi-chunk upload is allowed to be smaller than chunk_size.
    """
    if video_size <= _MAX_CHUNK:
        # Single-chunk upload: send the whole file in one PUT.
        # Setting chunk_size == video_size is always valid for count == 1.
        return video_size, 1

    # Multi-chunk upload: use the maximum chunk size to minimise round-trips.
    chunk_size = _MAX_CHUNK
    total_chunk_count = math.ceil(video_size / chunk_size)
    return chunk_size, total_chunk_count


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
    chunk_size, total_chunk_count = _compute_chunks(video_size)

    parts = description.split("\n\n", 1)
    short_title = parts[0]
    description = parts[1] if len(parts) > 1 else ""

    # Caption: TikTok allows 2200 chars; combine title + description
    caption = f"{title}\n\n{description}"[:2200]

    # ── Step 1: Initialise upload ─────────────────────────────────────────────
    init_body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        },
    }

    logger.info(
        f"Initialising TikTok upload for '{title}'… "
        f"({video_size} bytes, {total_chunk_count} chunk(s) of {chunk_size} bytes)"
    )
    logger.info(f"Init body: {json.dumps(init_body, indent=2)}")
    logger.info(f"Auth header: Bearer {access_token[:10]}...")

    with httpx.Client(timeout=30) as client:
        resp = client.post(TIKTOK_INIT_URL, headers=headers, json=init_body)

    # Always log the body before raising so failed responses are visible in logs.
    logger.info(f"Init response [{resp.status_code}]: {resp.text}")
    resp.raise_for_status()

    data = resp.json()
    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok init failed: {data}")

    upload_url = data["data"]["upload_url"]
    publish_id = data["data"]["publish_id"]

    # ── Step 2: Upload chunks ─────────────────────────────────────────────────
    logger.info("Uploading video chunks to TikTok…")
    video_bytes = video_path.read_bytes()
    chunks = [
        video_bytes[i : i + chunk_size]
        for i in range(0, video_size, chunk_size)
    ]

    for idx, chunk in enumerate(chunks):
        start = idx * chunk_size
        end = start + len(chunk) - 1
        chunk_headers = {
            "Content-Range": f"bytes {start}-{end}/{video_size}",
            "Content-Type": "video/mp4",
        }
        with httpx.Client(timeout=120) as client:
            put_resp = client.put(upload_url, headers=chunk_headers, content=chunk)

        logger.info(
            f"Chunk {idx + 1}/{len(chunks)} response [{put_resp.status_code}]: "
            f"{put_resp.text[:200]}"
        )
        put_resp.raise_for_status()
        logger.info(f"Chunk {idx + 1}/{len(chunks)} uploaded ({len(chunk)} bytes).")

    # ── Step 3: Poll status ───────────────────────────────────────────────────
    logger.info("Polling TikTok publish status…")
    for attempt in range(20):
        time.sleep(10)
        status_body = {"publish_id": publish_id}
        with httpx.Client(timeout=30) as client:
            st_resp = client.post(TIKTOK_STATUS_URL, headers=headers, json=status_body)

        logger.info(f"Status poll {attempt + 1} [{st_resp.status_code}]: {st_resp.text}")
        st_resp.raise_for_status()

        st_data = st_resp.json()
        status = st_data.get("data", {}).get("status", "")
        logger.info(f"TikTok status: {status}")

        if status == "SEND_TO_USER_INBOX":
            logger.info("Upload complete and sent to TikTok inbox.")
            return publish_id
        if status in ("FAILED", "PUBLISH_FAILED"):
            raise RuntimeError(f"TikTok publish failed: {st_data}")

    logger.warning("TikTok status polling timed out — video may still be processing.")
    return publish_id
