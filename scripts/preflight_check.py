#!/usr/bin/env python3
"""
preflight_check.py — validates all required environment variables before the
pipeline runs. Called as the first step in every GitHub Actions workflow.

Exit codes:
  0  all checks passed
  1  one or more checks failed (workflow should halt)

Usage:
    python scripts/preflight_check.py --channel factsunlocked
    python scripts/preflight_check.py --channel astrofacts
    python scripts/preflight_check.py --channel astrofacts --skip-tiktok
"""

import argparse
import os
import sys
import httpx

# ── ANSI colours (work in GitHub Actions logs) ────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✔{RESET}  {msg}")
def fail(msg):  print(f"  {RED}✘{RESET}  {BOLD}{msg}{RESET}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


# ── Individual check helpers ──────────────────────────────────────────────────

def check_env_present(name: str) -> bool:
    val = os.environ.get(name, "").strip()
    if val:
        ok(f"{name} is set ({len(val)} chars)")
        return True
    fail(f"{name} is MISSING or empty — add it as a GitHub Actions secret")
    return False


def check_groq_token(env_name: str) -> bool:
    """Validate Groq token by calling the /models endpoint."""
    token = os.environ.get(env_name, "").strip()
    if not token:
        fail(f"{env_name}: cannot test — key is missing")
        return False
    try:
        resp = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            ok(f"{env_name}: Groq token is valid (HTTP 200)")
            return True
        elif resp.status_code == 401:
            fail(f"{env_name}: Groq token is INVALID (401 Unauthorized)")
            return False
        else:
            warn(f"{env_name}: unexpected Groq response {resp.status_code} — treating as warning")
            return True   # don't block on unexpected status
    except Exception as e:
        warn(f"{env_name}: Groq connectivity check failed ({e}) — treating as warning")
        return True   # network hiccup shouldn't abort the run


def check_youtube_token(client_id_env: str, client_secret_env: str, refresh_token_env: str) -> bool:
    """Validate YouTube OAuth by exchanging the refresh token."""
    client_id     = os.environ.get(client_id_env, "").strip()
    client_secret = os.environ.get(client_secret_env, "").strip()
    refresh_token = os.environ.get(refresh_token_env, "").strip()

    # Presence already checked separately; here we actually test the token exchange
    if not all([client_id, client_secret, refresh_token]):
        fail("YouTube: cannot test token exchange — one or more credentials missing")
        return False

    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and "access_token" in data:
            ok(f"YouTube OAuth exchange succeeded ({client_id_env[:30]}…)")
            return True
        error = data.get("error", resp.status_code)
        error_desc = data.get("error_description", "")
        fail(f"YouTube OAuth FAILED: {error} — {error_desc}")
        print(f"      Check {client_id_env}, {client_secret_env}, {refresh_token_env}")
        return False
    except Exception as e:
        warn(f"YouTube OAuth connectivity check failed ({e}) — treating as warning")
        return True


def check_tiktok_token(client_key_env: str, client_secret_env: str, refresh_token_env: str) -> bool:
    """Validate TikTok credentials by refreshing the access token."""
    client_key    = os.environ.get(client_key_env, "").strip()
    client_secret = os.environ.get(client_secret_env, "").strip()
    refresh_token = os.environ.get(refresh_token_env, "").strip()

    if not all([client_key, client_secret, refresh_token]):
        fail("TikTok: cannot test token refresh — one or more credentials missing")
        return False

    try:
        resp = httpx.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        data = resp.json()
        token_data = data.get("data", {}) or data
        err = data.get("error", {})

        if resp.status_code == 200 and token_data.get("access_token"):
            ok(f"TikTok token refresh succeeded ({client_key_env[:30]}…)")
            return True

        err_code = err.get("code", resp.status_code)
        err_msg  = err.get("message", "unknown error")
        fail(f"TikTok token refresh FAILED: {err_code} — {err_msg}")
        print(f"      Check {client_key_env}, {client_secret_env}, {refresh_token_env}")
        return False
    except Exception as e:
        warn(f"TikTok connectivity check failed ({e}) — treating as warning")
        return True


# ── Channel check suites ──────────────────────────────────────────────────────

def check_factsunlocked() -> list[bool]:
    results = []
    header("① Groq API key (FactsUnlocked)")
    results.append(check_env_present("GROQ_API_KEY"))
    results.append(check_groq_token("GROQ_API_KEY"))

    header("② YouTube credentials (FactsUnlocked)")
    results.append(check_env_present("YOUTUBE_CLIENT_ID"))
    results.append(check_env_present("YOUTUBE_CLIENT_SECRET"))
    results.append(check_env_present("YOUTUBE_REFRESH_TOKEN"))
    results.append(check_youtube_token(
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
    ))
    return results


def check_astrofacts(skip_tiktok: bool = False) -> list[bool]:
    results = []
    header("① Groq API key (AstroFacts)")
    results.append(check_env_present("GROQ_API_KEY_ASTRO"))
    results.append(check_groq_token("GROQ_API_KEY_ASTRO"))

    header("② YouTube credentials (AstroFacts)")
    results.append(check_env_present("YOUTUBE_CLIENT_ID_ASTRO"))
    results.append(check_env_present("YOUTUBE_CLIENT_SECRET_ASTRO"))
    results.append(check_env_present("YOUTUBE_REFRESH_TOKEN_ASTRO"))
    results.append(check_youtube_token(
        "YOUTUBE_CLIENT_ID_ASTRO",
        "YOUTUBE_CLIENT_SECRET_ASTRO",
        "YOUTUBE_REFRESH_TOKEN_ASTRO",
    ))

    if skip_tiktok:
        warn("TikTok checks skipped (--skip-tiktok flag set)")
    else:
        header("③ TikTok credentials (AstroFacts)")
        results.append(check_env_present("TIKTOK_CLIENT_KEY_ASTRO"))
        results.append(check_env_present("TIKTOK_CLIENT_SECRET_ASTRO"))
        results.append(check_env_present("TIKTOK_REFRESH_TOKEN_ASTRO"))
        results.append(check_tiktok_token(
            "TIKTOK_CLIENT_KEY_ASTRO",
            "TIKTOK_CLIENT_SECRET_ASTRO",
            "TIKTOK_REFRESH_TOKEN_ASTRO",
        ))
    return results


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pre-flight credential check")
    parser.add_argument(
        "--channel",
        choices=["factsunlocked", "astrofacts"],
        required=True,
    )
    parser.add_argument(
        "--skip-tiktok",
        action="store_true",
        help="Skip TikTok checks (use when tiktok.enabled=false in settings.yaml)",
    )
    args = parser.parse_args()

    print(f"\n{'═'*55}")
    print(f"  🔍 Preflight check — {args.channel.upper()}")
    print(f"{'═'*55}")

    if args.channel == "factsunlocked":
        results = check_factsunlocked()
    else:
        results = check_astrofacts(skip_tiktok=args.skip_tiktok)

    # ── Summary ──────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print(f"\n{'═'*55}")
    if all(results):
        print(f"  {GREEN}{BOLD}✔ All {total} checks passed — pipeline is clear to run.{RESET}")
        print(f"{'═'*55}\n")
        sys.exit(0)
    else:
        failed = [i for i, r in enumerate(results) if not r]
        print(f"  {RED}{BOLD}✘ {len(failed)} of {total} checks FAILED.{RESET}")
        print(f"  Fix the secrets above, then re-run the workflow.")
        print(f"{'═'*55}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
