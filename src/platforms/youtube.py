"""
YouTubePublisher – uploads videos via YouTube Data API v3.
Supports playlist assignment (used by AstroFacts for daily/weekly/monthly/yearly).
"""

import os
import json
from pathlib import Path
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _get_youtube_service(client_id_env, client_secret_env, refresh_token_env):
    """Build an authenticated YouTube service object."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ[refresh_token_env],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ[client_id_env],
        client_secret=os.environ[client_secret_env],
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube"],
    )
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list,
    category_id: str = "28",
    privacy: str = "public",
    made_for_kids: bool = False,
    thumbnail_path: str = None,
    playlist_id: str = None,
    # Env-var names (different per channel)
    client_id_env: str = "YOUTUBE_CLIENT_ID",
    client_secret_env: str = "YOUTUBE_CLIENT_SECRET",
    refresh_token_env: str = "YOUTUBE_REFRESH_TOKEN",
) -> str:
    """
    Upload a video and optionally add it to a playlist.
    Returns the YouTube video ID.
    """
    from googleapiclient.http import MediaFileUpload

    youtube = _get_youtube_service(client_id_env, client_secret_env, refresh_token_env)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "madeForKids": made_for_kids,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,  # 5MB chunks
    )

    logger.info(f"Uploading '{title}' to YouTube…")
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    logger.info(f"Uploaded: https://youtube.com/shorts/{video_id}")

    video_id = response["id"]
    logger.info(f"Uploaded: https://youtube.com/shorts/{video_id}")

    # Upload thumbnail if provided
    if thumbnail_path and Path(thumbnail_path).exists():
        from googleapiclient.http import MediaFileUpload as _MFU
        logger.info("Uploading thumbnail…")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=_MFU(thumbnail_path, mimetype="image/png", resumable=True),
        ).execute()
        logger.info("Thumbnail set.")

    # Add to playlist if provided
    if playlist_id:
        add_to_playlist(youtube, video_id, playlist_id)

    # Add to playlist if provided
    if playlist_id:
        add_to_playlist(youtube, video_id, playlist_id)

    return video_id


def add_to_playlist(youtube, video_id: str, playlist_id: str) -> None:
    """Add an uploaded video to a YouTube playlist."""
    logger.info(f"Adding {video_id} to playlist {playlist_id}")
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()
    logger.info("Added to playlist.")
