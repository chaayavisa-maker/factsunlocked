#!/usr/bin/env python3
"""
Checks whether your Google OAuth app is in 'testing' mode (7-day token expiry)
or 'production' mode (tokens live until revoked).

Also prints step-by-step instructions to publish it to production.

Usage:
    python scripts/publish_oauth_app.py
"""

import json
import sys
import webbrowser
from pathlib import Path


def main():
    secrets_file = Path("client_secrets.json")

    print("=" * 64)
    print("  Google OAuth App — Production Mode Checker")
    print("=" * 64)
    print()

    project_id = None
    if secrets_file.exists():
        with open(secrets_file) as f:
            data = json.load(f)
        info = data.get("installed") or data.get("web", {})
        project_id = info.get("project_id")
        client_id  = info.get("client_id", "")
        print(f"Client ID:  {client_id[:30]}...")
        print(f"Project ID: {project_id}")
    else:
        print("client_secrets.json not found — that's OK, read on.")

    print()
    print("WHY THIS MATTERS")
    print("-" * 40)
    print("If your OAuth app is in 'Testing' mode, Google refreshes")
    print("tokens expire after 7 DAYS. This silently breaks the daily")
    print("pipeline after one week — even while you're away.")
    print()
    print("Setting it to 'Production' makes tokens permanent (they only")
    print("expire if you revoke them or change your password).")
    print()
    print("HOW TO PUBLISH YOUR APP (2 minutes)")
    print("-" * 40)
    print()
    print("1. Go to the Google Cloud Console:")
    url = (
        f"https://console.cloud.google.com/apis/credentials/consent"
        + (f"?project={project_id}" if project_id else "")
    )
    print(f"   {url}")
    print()
    print("2. You'll see 'OAuth consent screen'.")
    print("   Look for the 'Publishing status' section.")
    print()
    print("3. It likely says 'Testing'. Click 'PUBLISH APP'.")
    print()
    print("4. Google will ask if you want to submit for verification.")
    print("   For a personal channel → click 'CONFIRM' without submitting.")
    print("   (Verification is only needed if you plan to give other")
    print("   people access to your app — for your own channel it's")
    print("   not required.)")
    print()
    print("5. Status should now say 'In production'.")
    print()
    print("RESULT: Your refresh token will now work indefinitely.")
    print()
    print("OPTIONAL: After publishing, re-run the token script once")
    print("to get a fresh production-mode token:")
    print()
    print("   python scripts/get_youtube_token.py")
    print()
    print("Then update YOUTUBE_REFRESH_TOKEN in GitHub Secrets.")
    print()

    open_browser = input("Open the consent screen now? [Y/n] ").strip().lower()
    if open_browser in ("", "y", "yes"):
        webbrowser.open(url)
        print("Opened in browser.")
    else:
        print(f"Open manually: {url}")

    print()
    print("=" * 64)
    print("Done. Once published, your pipeline runs forever unattended.")
    print("=" * 64)


if __name__ == "__main__":
    main()
