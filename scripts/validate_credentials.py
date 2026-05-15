#!/usr/bin/env python3
"""
Validates all external credentials and API connectivity.
Run as a pre-flight check in GitHub Actions, or standalone.

Exit code 0 = all good
Exit code 1 = one or more checks failed (pipeline should abort)
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Make sure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.logger import setup_logger

logger = setup_logger("validate")

RESULTS = {}


def check(name: str):
    """Decorator that records pass/fail for each check."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                fn(*args, **kwargs)
                RESULTS[name] = "✅ PASS"
                logger.info(f"  {name}: PASS")
            except Exception as e:
                RESULTS[name] = f"❌ FAIL — {e}"
                logger.error(f"  {name}: FAIL — {e}")
        return wrapper
    return decorator


# ── Groq ─────────────────────────────────────────────────────────────────────

@check("Groq API")
def validate_groq():
    key = os.environ.get("GROQ_API_KEY", "")
    if not key or key.startswith("your_"):
        raise ValueError("GROQ_API_KEY is not set")

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",   # smallest/fastest for validation
            "messages": [{"role": "user", "content": "Reply with the word ALIVE only."}],
            "max_tokens": 5,
        },
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    content = body["choices"][0]["message"]["content"]
    if not content:
        raise ValueError("Empty response from Groq")


# ── Pollinations.ai ───────────────────────────────────────────────────────────

@check("Pollinations.ai (image API)")
def validate_pollinations():
    # Fetch a tiny test image — 64×64 is near-instant
    url = "https://image.pollinations.ai/prompt/test?width=64&height=64&nologo=true"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    if len(resp.content) < 500:
        raise ValueError(f"Suspiciously small response: {len(resp.content)} bytes")


# ── edge-tts ──────────────────────────────────────────────────────────────────

@check("edge-tts (TTS)")
def validate_edge_tts():
    import asyncio
    import edge_tts
    import tempfile

    async def _test():
        out = tempfile.mktemp(suffix=".mp3")
        comm = edge_tts.Communicate("test", voice="en-US-AriaNeural")
        await comm.save(out)
        size = Path(out).stat().st_size
        Path(out).unlink(missing_ok=True)
        if size < 500:
            raise ValueError(f"TTS output too small: {size} bytes")

    asyncio.run(_test())


# ── YouTube OAuth ─────────────────────────────────────────────────────────────

@check("YouTube OAuth token")
def validate_youtube():
    client_id     = os.environ.get("YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

    for name, val in [
        ("YOUTUBE_CLIENT_ID", client_id),
        ("YOUTUBE_CLIENT_SECRET", client_secret),
        ("YOUTUBE_REFRESH_TOKEN", refresh_token),
    ]:
        if not val or val.startswith("your_"):
            raise ValueError(f"{name} is not set")

    # Attempt a token refresh — this is the real test
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type":    "refresh_token",
        },
        timeout=15,
    )

    body = resp.json()

    if "error" in body:
        err = body.get("error", "unknown")
        desc = body.get("error_description", "")
        if err == "invalid_grant":
            raise ValueError(
                "Refresh token has expired or been revoked. "
                "Re-run: python scripts/get_youtube_token.py  "
                "and update the YOUTUBE_REFRESH_TOKEN secret."
            )
        raise ValueError(f"OAuth error: {err} — {desc}")

    access_token = body.get("access_token", "")
    if not access_token:
        raise ValueError("No access_token in response")

    # Verify the token actually has YouTube scope
    info = requests.get(
        "https://www.googleapis.com/oauth2/v1/tokeninfo",
        params={"access_token": access_token},
        timeout=10,
    ).json()

    scope = info.get("scope", "")
    if "youtube" not in scope:
        raise ValueError(f"Token does not have YouTube scope. Got: {scope}")


# ── ffmpeg ────────────────────────────────────────────────────────────────────

@check("ffmpeg binary")
def validate_ffmpeg():
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError("ffmpeg not found or failed")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    logger.info("=== Credential / connectivity validation ===")

    validate_groq()
    validate_pollinations()
    validate_edge_tts()
    validate_youtube()
    validate_ffmpeg()

    logger.info("")
    logger.info("=== Results ===")
    all_pass = True
    for name, status in RESULTS.items():
        logger.info(f"  {status}  {name}")
        if "FAIL" in status:
            all_pass = False

    logger.info("")

    if all_pass:
        logger.info("All checks passed. Pipeline is good to run.")
        # Write a status file for GitHub Actions to pick up
        Path("validation_status.json").write_text(
            json.dumps({"status": "ok", "checks": RESULTS}, default=str)
        )
        sys.exit(0)
    else:
        failed = [n for n, s in RESULTS.items() if "FAIL" in s]
        logger.error(f"FAILED checks: {', '.join(failed)}")
        Path("validation_status.json").write_text(
            json.dumps({"status": "failed", "checks": RESULTS}, default=str)
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
