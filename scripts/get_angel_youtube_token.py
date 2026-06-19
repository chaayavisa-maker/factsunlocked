#!/usr/bin/env python3
"""
One-time YouTube OAuth setup for AngelNumbers channel.

Usage:
    python scripts/get_angel_youtube_token.py

Reads: client_secrets_angel.json  (download from Google Cloud Console)
Prints the three values to add as GitHub Actions secrets:
    YOUTUBE_CLIENT_ID_ANGEL
    YOUTUBE_CLIENT_SECRET_ANGEL
    YOUTUBE_REFRESH_TOKEN_ANGEL
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Install: pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

SECRETS_FILE = Path(__file__).parent.parent / "client_secrets_angel.json"


def main():
    if not SECRETS_FILE.exists():
        print(f"ERROR: {SECRETS_FILE} not found.")
        print(
            "Download OAuth credentials from Google Cloud Console "
            "(for the AngelNumbers project) and save as client_secrets_angel.json"
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
    creds = flow.run_local_server(port=8082, prompt="consent", access_type="offline")

    with open(SECRETS_FILE) as f:
        secrets = json.load(f)
    client_info = secrets.get("installed", secrets.get("web", {}))

    print("\n" + "=" * 60)
    print("AngelNumbers YouTube secrets — add to GitHub Actions:")
    print("=" * 60)
    print(f"YOUTUBE_CLIENT_ID_ANGEL     = {client_info.get('client_id', '?')}")
    print(f"YOUTUBE_CLIENT_SECRET_ANGEL = {client_info.get('client_secret', '?')}")
    print(f"YOUTUBE_REFRESH_TOKEN_ANGEL = {creds.refresh_token}")
    print("=" * 60)


if __name__ == "__main__":
    main()
