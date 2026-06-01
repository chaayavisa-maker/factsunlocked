#!/usr/bin/env python3
"""
One-time setup script to obtain TikTok OAuth tokens.

Run once locally:
    python scripts/get_tiktok_token.py

It will:
  1. Open your browser to TikTok's auth page
  2. Ask you to paste back the redirect URL
  3. Print TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
     — copy these into your GitHub Actions secrets.
"""

import os
import sys
import secrets
import webbrowser
import urllib.parse
import requests

# ── Fill these in (or set as env vars) ──────────────────────────────────────
CLIENT_KEY    = os.getenv("TIKTOK_CLIENT_KEY",    input("Paste your TikTok Client Key: ").strip())
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", input("Paste your TikTok Client Secret: ").strip())
# ────────────────────────────────────────────────────────────────────────────

REDIRECT_URI = "https://localhost/"          # Must match your TikTok app settings
SCOPES       = "user.info.basic,video.publish,video.upload"
STATE        = secrets.token_urlsafe(16)

auth_url = (
    "https://www.tiktok.com/v2/auth/authorize/?"
    + urllib.parse.urlencode({
        "client_key":     CLIENT_KEY,
        "response_type":  "code",
        "scope":          SCOPES,
        "redirect_uri":   REDIRECT_URI,
        "state":          STATE,
    })
)

print("\n📱 Opening TikTok auth page in your browser...")
print("   If it doesn't open, visit this URL manually:\n")
print(f"   {auth_url}\n")
webbrowser.open(auth_url)

print("After you click 'Authorize', TikTok will redirect to:")
print("  https://localhost/?code=XXXX&state=YYYY\n")
redirect = input("Paste the full redirect URL here: ").strip()

parsed = urllib.parse.urlparse(redirect)
params = urllib.parse.parse_qs(parsed.query)

if "code" not in params:
    print("❌ No 'code' found in URL. Did you paste it correctly?")
    sys.exit(1)

code = params["code"][0]
print(f"\n✅ Got auth code: {code[:8]}…")

# Exchange code for tokens
resp = requests.post(
    "https://open.tiktokapis.com/v2/oauth/token/",
    data={
        "client_key":    CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  REDIRECT_URI,
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=30,
)
resp.raise_for_status()
data = resp.json()

if data.get("error"):
    print(f"❌ Token exchange failed: {data}")
    sys.exit(1)

refresh_token = data["refresh_token"]

print("\n" + "="*60)
print("✅  SUCCESS — Add these three secrets to GitHub Actions:")
print("="*60)
print(f"\n  TIKTOK_CLIENT_KEY     = {CLIENT_KEY}")
print(f"  TIKTOK_CLIENT_SECRET  = {CLIENT_SECRET}")
print(f"  TIKTOK_REFRESH_TOKEN  = {refresh_token}")
print("\n" + "="*60)
print("  Repo → Settings → Secrets → Actions → New repository secret")
print("="*60 + "\n")
