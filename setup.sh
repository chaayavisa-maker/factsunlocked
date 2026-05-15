#!/usr/bin/env bash
# setup.sh — one-time local setup + smoke-test
set -euo pipefail

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   FactsUnlocked — Local Setup                ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Python version check ────────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python)
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: $PY_VERSION"
if [[ "$PY_VERSION" < "3.10" ]]; then
  echo "ERROR: Python 3.10+ required."
  exit 1
fi

# ── FFmpeg check ─────────────────────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
  echo "ERROR: ffmpeg not found."
  echo "  macOS:  brew install ffmpeg"
  echo "  Ubuntu: sudo apt install ffmpeg"
  echo "  Windows: https://ffmpeg.org/download.html"
  exit 1
fi
echo "FFmpeg: $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3)"

# ── Install Python deps ───────────────────────────────────────────────────────
echo ""
echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "Dependencies installed."

# ── .env file ────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cat > .env << 'EOF'
# Copy this file and fill in your values.
# For production use GitHub Actions Secrets instead.
GROQ_API_KEY=your_groq_api_key_here
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
YOUTUBE_REFRESH_TOKEN=your_refresh_token_here
YOUTUBE_PRIVACY=public
EOF
  echo ".env file created — fill in your API keys."
else
  echo ".env already exists."
fi

# ── .gitignore ────────────────────────────────────────────────────────────────
cat > .gitignore << 'EOF'
.env
.youtube_token.json
client_secrets.json
workspace/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.egg-info/
dist/
build/
.venv/
venv/
EOF
echo ".gitignore written."

# ── Smoke test ────────────────────────────────────────────────────────────────
echo ""
echo "Running smoke test (imports only — no API calls)..."

export PYTHONPATH="$(pwd)/src"
$PYTHON - << 'PYEOF'
import sys

errors = []

try:
    from agents.topic_agent import TopicAgent
    from agents.script_agent import ScriptAgent
    from agents.image_agent import ImageAgent
    from agents.narration_agent import NarrationAgent
    from agents.video_agent import VideoAgent
    from agents.seo_agent import SEOAgent
    from platforms.youtube import YouTubePublisher
    print("  ✓ All agent imports OK")
except ImportError as e:
    errors.append(str(e))
    print(f"  ✗ Import error: {e}")

try:
    import moviepy.editor
    print("  ✓ moviepy OK")
except ImportError as e:
    errors.append(str(e))

try:
    import PIL.Image
    print("  ✓ Pillow OK")
except ImportError as e:
    errors.append(str(e))

try:
    import edge_tts
    print("  ✓ edge-tts OK")
except ImportError as e:
    errors.append(str(e))

try:
    import groq
    print("  ✓ groq OK")
except ImportError as e:
    errors.append(str(e))

if errors:
    print(f"\n  {len(errors)} import(s) failed. Run: pip install -r requirements.txt")
    sys.exit(1)
else:
    print("\n  All checks passed.")
PYEOF

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Setup complete!                            ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  Next steps:                                 ║"
echo "║  1. Get free Groq API key:                   ║"
echo "║     https://console.groq.com                ║"
echo "║  2. Set up YouTube credentials:              ║"
echo "║     python scripts/get_youtube_token.py      ║"
echo "║  3. Fill in .env (for local testing)         ║"
echo "║  4. Test locally:                            ║"
echo "║     source .env && python src/main.py        ║"
echo "║  5. Push to GitHub + add Secrets             ║"
echo "║     → pipeline runs automatically at 09:00  ║"
echo "║       UTC every day                          ║"
echo "╚══════════════════════════════════════════════╝"
