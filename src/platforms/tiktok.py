"""
TikTok Content Posting API v2 publisher.
Handles token refresh + chunked video upload.
"""

import os
import math
import time
import requests
from pathlib import Path
from utils.logger import get_logger

log = get_logger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB per chunk (TikTok min is 5 MB)


# ─── Token management ────────────────────────────────────────────────────────

def _refresh_access_token() -> str:
    """Exchange the stored refresh token for a fresh access token."""
    client_key    = os.environ["TIKTOK_CLIENT_KEY"]
    client_secret = os.environ["TIKTOK_CLIENT_SECRET"]
    refresh_token = os.environ["TIKTOK_REFRESH_TOKEN"]

    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key":    client_key,
            "client_secret": client_secret,
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"TikTok token refresh failed: {data}")

    log.info("TikTok access token refreshed (expires in %ss)", data.get("expires_in"))
    return data["access_token"]


# ─── Upload helpers ───────────────────────────────────────────────────────────

def _init_upload(access_token: str, file_size: int, chunk_count: int,
                 title: str, privacy: str) -> dict:
    """Call the /post/publish/video/init/ endpoint."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json; charset=UTF-8",
    }
    body = {
        "post_info": {
            "title":           title[:2200],   # TikTok max caption length
            "privacy_level":   privacy,         # PUBLIC_TO_EVERYONE | SELF_ONLY | MUTUAL_FOLLOW_FRIENDS
            "disable_duet":    False,
            "disable_comment": False,
            "disable_stitch":  False,
        },
        "source_info": {
            "source":      "FILE_UPLOAD",
            "video_size":  file_size,
            "chunk_size":  CHUNK_SIZE,
            "total_chunk_count": chunk_count,
        },
    }
    resp = requests.post(
        f"{TIKTOK_API_BASE}/post/publish/video/init/",
        json=body,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error", {}).get("code") not in ("ok", None, ""):
        raise RuntimeError(f"TikTok init upload failed: {data}")
    return data["data"]


def _upload_chunk(upload_url: str, chunk_data: bytes,
                  chunk_index: int, file_size: int) -> None:
    """PUT one chunk to TikTok's upload URL."""
    start = chunk_index * CHUNK_SIZE
    end   = min(start + len(chunk_data), file_size) - 1
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Type":  "video/mp4",
        "Content-Length": str(len(chunk_data)),
    }
    resp = requests.put(upload_url, data=chunk_data, headers=headers, timeout=120)
    if resp.status_code not in (200, 206):
        raise RuntimeError(
            f"TikTok chunk {chunk_index} upload failed "
            f"({resp.status_code}): {resp.text}"
        )
    log.debug("Chunk %d uploaded ✓", chunk_index)


def _poll_publish_status(access_token: str, publish_id: str,
                         max_wait: int = 300) -> None:
    """Poll until the video is published or an error is returned."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json; charset=UTF-8",
    }
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.post(
            f"{TIKTOK_API_BASE}/post/publish/status/fetch/",
            json={"publish_id": publish_id},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status")
        log.info("TikTok publish status: %s", status)

        if status == "PUBLISH_COMPLETE":
            log.info("✅ TikTok video published! publish_id=%s", publish_id)
            return
        if status in ("FAILED", "PUBLISH_FAILED"):
            raise RuntimeError(f"TikTok publishing failed: {data}")

        time.sleep(10)

    raise TimeoutError(f"TikTok publish did not complete within {max_wait}s")


# ─── Public entry point ───────────────────────────────────────────────────────

def upload_to_tiktok(video_path: str, title: str,
                     privacy: str = "PUBLIC_TO_EVERYONE") -> str:
    """
    Upload *video_path* to TikTok and return the publish_id.

    Required env vars:
        TIKTOK_CLIENT_KEY
        TIKTOK_CLIENT_SECRET
        TIKTOK_REFRESH_TOKEN
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size   = video_path.stat().st_size
    chunk_count = math.ceil(file_size / CHUNK_SIZE)
    log.info("Uploading to TikTok: %s (%.1f MB, %d chunks)",
             video_path.name, file_size / 1e6, chunk_count)

    access_token = _refresh_access_token()
    init_data    = _init_upload(access_token, file_size, chunk_count, title, privacy)
    publish_id   = init_data["publish_id"]
    upload_url   = init_data["upload_url"]
    log.info("TikTok publish_id: %s", publish_id)

    # Upload chunks
    with open(video_path, "rb") as f:
        for idx in range(chunk_count):
            chunk = f.read(CHUNK_SIZE)
            _upload_chunk(upload_url, chunk, idx, file_size)

    # Poll for completion
    _poll_publish_status(access_token, publish_id)
    return publish_id
