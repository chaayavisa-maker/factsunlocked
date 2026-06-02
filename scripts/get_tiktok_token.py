#!/usr/bin/env python3
"""
One-time TikTok OAuth setup for AstroFacts.

Usage:
    python scripts/get_tiktok_token.py

Prerequisites:
    1. Create a TikTok developer app at https://developers.tiktok.com
    2. Enable "Content Posting API" scope
    3. Set redirect URI to: http://localhost:8080/callback
    4. Set env vars: TIKTOK_CLIENT_KEY_ASTRO, TIKTOK_CLIENT_SECRET_ASTRO

After running, add the printed tokens to GitHub Actions secrets.
"""

import os
import sys
import json
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx

CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY_ASTRO", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET_ASTRO", "")
REDIRECT_URI = "http://localhost:8080/callback"
SCOPE = "video.upload"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h1>Auth complete! You can close this window.</h1>")

    def log_message(self, format, *args):
        pass


def main():
    if not CLIENT_KEY or not CLIENT_SECRET:
        print("ERROR: Set TIKTOK_CLIENT_KEY_ASTRO and TIKTOK_CLIENT_SECRET_ASTRO first.")
        sys.exit(1)

    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPE,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
    }
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print(f"\nOpening TikTok auth URL in your browser...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    print("Waiting for TikTok callback on http://localhost:8080/callback ...")
    server.handle_request()

    if not auth_code:
        print("ERROR: No auth code received.")
        sys.exit(1)

    # Exchange code for tokens
    payload = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }
    resp = httpx.post(TOKEN_URL, data=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    token_data = data.get("data", {})
    print("\n" + "=" * 60)
    print("TikTok tokens — add these to GitHub Actions secrets:")
    print("=" * 60)
    print(f"TIKTOK_REFRESH_TOKEN_ASTRO = {token_data.get('refresh_token', '?')}")
    print("=" * 60)
    print(f"\nAccess token (expires in {token_data.get('expires_in', '?')}s):")
    print(f"  {token_data.get('access_token', '?')}")


if __name__ == "__main__":
    main()
