import os
import time
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from utils.logger import setup_logger

logger = setup_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# Resumable upload chunk size — 8 MB
CHUNK_SIZE = 8 * 1024 * 1024

# YouTube API quota-safe retry errors
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}


class YouTubePublisher:
    def __init__(self):
        self.creds = self._build_credentials()
        self.service = build("youtube", "v3", credentials=self.creds)

    def _build_credentials(self) -> Credentials:
        """
        Builds OAuth2 credentials from env vars.
        YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
        must be set (store them as GitHub Actions secrets).
        """
        creds = Credentials(
            token=None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=SCOPES,
        )
        creds.refresh(Request())
        logger.info("YouTube credentials refreshed.")
        return creds

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=5, max=60))
    def upload(self, video_path: Path, metadata: dict) -> str:
        """
        Uploads video to YouTube as a Short.
        Returns the YouTube video ID on success.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.info(f"Uploading {video_path.name} ({file_size_mb:.1f} MB) ...")

        # Force #Shorts in description if not present
        description = metadata["description"]
        if "#Shorts" not in description and "#shorts" not in description:
            description = "#Shorts\n\n" + description

        body = {
            "snippet": {
                "title": metadata["title"],
                "description": description,
                "tags": metadata.get("tags", []),
                "categoryId": metadata.get("category_id", "27"),
                "defaultLanguage": metadata.get("default_language", "en"),
            },
            "status": {
                "privacyStatus": os.environ.get("YOUTUBE_PRIVACY", "public"),
                "selfDeclaredMadeForKids": False,
                "notifySubscribers": True,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            chunksize=CHUNK_SIZE,
            resumable=True,
        )

        request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        video_id = self._resumable_upload(request)
        url = f"https://www.youtube.com/shorts/{video_id}"
        logger.info(f"✓ Published! {url}")
        return video_id

    def _resumable_upload(self, request) -> str:
        """Executes a resumable upload with retry on transient errors."""
        response = None
        error = None
        retry_count = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"  Upload progress: {pct}%")
            except HttpError as e:
                if e.resp.status in RETRIABLE_STATUS_CODES:
                    error = f"HTTP {e.resp.status}: {e.content}"
                else:
                    raise
            except Exception as e:
                error = str(e)

            if error:
                retry_count += 1
                if retry_count > 10:
                    raise RuntimeError(f"Upload failed after 10 retries: {error}")
                wait = min(2 ** retry_count, 64)
                logger.warning(f"  Upload error ({error}). Retrying in {wait}s ...")
                time.sleep(wait)
                error = None

        return response["id"]

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> None:
        """Optional: set a custom thumbnail (requires verification)."""
        if not thumbnail_path.exists():
            logger.warning("Thumbnail file not found — skipping.")
            return
        try:
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
            ).execute()
            logger.info("Custom thumbnail set.")
        except HttpError as e:
            logger.warning(f"Could not set thumbnail: {e}")
