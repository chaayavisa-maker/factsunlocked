#!/usr/bin/env python3
"""
Run this ONCE locally to get your YouTube OAuth2 refresh token.
The token is then stored as a GitHub Actions secret.

Usage:
    pip install google-auth-oauthlib
    python scripts/get_youtube_token.py

You'll be redirected to a browser. Authorise the app.
The script prints your refresh_token — copy it to GitHub Secrets.
"""

import json
import os
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Run:  pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

def main():
    print("=" * 60)
    print("  YouTube OAuth2 Refresh Token Generator")
    print("=" * 60)
    print()

    # Try to load client_secrets.json (downloaded from Google Cloud Console)
    secrets_file = Path("client_secrets.json")

    if not secrets_file.exists():
        print("ERROR: client_secrets.json not found.")
        print()
        print("Steps to create it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project (or select existing)")
        print("  3. Enable 'YouTube Data API v3'")
        print("  4. Go to APIs & Services → Credentials")
        print("  5. Create 'OAuth 2.0 Client ID' → Desktop app")
        print("  6. Download JSON → save as client_secrets.json in this folder")
        print()
        sys.exit(1)

    print("Opening browser for authorisation...")
    print("(If it doesn't open, copy the URL printed below)")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(secrets_file),
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )

    # Use local server for convenience
    creds = flow.run_local_server(
        port=8080,
        prompt="consent",
        access_type="offline",
    )

    print()
    print("=" * 60)
    print("  SUCCESS — Add these to GitHub Actions Secrets:")
    print("=" * 60)

    # Parse client_id / client_secret from the secrets file
    with open(secrets_file) as f:
        secrets_data = json.load(f)
    client_info = secrets_data.get("installed") or secrets_data.get("web", {})

    print()
    print(f"Secret name:  YOUTUBE_CLIENT_ID")
    print(f"Secret value: {client_info.get('client_id', 'NOT FOUND')}")
    print()
    print(f"Secret name:  YOUTUBE_CLIENT_SECRET")
    print(f"Secret value: {client_info.get('client_secret', 'NOT FOUND')}")
    print()
    print(f"Secret name:  YOUTUBE_REFRESH_TOKEN")
    print(f"Secret value: {creds.refresh_token}")
    print()
    print("=" * 60)
    print("Go to: https://github.com/<YOU>/<REPO>/settings/secrets/actions")
    print("Add all three secrets above, then push your code.")
    print("=" * 60)

    # Also save locally for reference (gitignored)
    token_path = Path(".youtube_token.json")
    token_path.write_text(json.dumps({
        "client_id": client_info.get("client_id"),
        "client_secret": client_info.get("client_secret"),
        "refresh_token": creds.refresh_token,
    }, indent=2))
    print(f"\nAlso saved to {token_path} (keep it safe, it's gitignored).")


if __name__ == "__main__":
    main()
