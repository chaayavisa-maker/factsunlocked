# 🎬 FactsUnlocked — Autonomous YouTube Shorts Business

> A fully automated pipeline that researches trending topics, writes scripts, generates images and narration, assembles polished vertical videos, and publishes them to YouTube — every single day — without you touching anything after setup.

---

## 💰 How It Makes Money

| Phase | Requirement | Timeline |
|---|---|---|
| **YouTube Partner Program** (Shorts) | 500 subs + 3,000 watch hours | 2–4 months |
| **Full AdSense** | 1,000 subs + 4,000 watch hours | 4–8 months |
| **Affiliate links** (Amazon, ClickBank) | Added to every description from day 1 | Immediate |
| **Sponsorships** | ~10K subs | 6–12 months |

Estimated at scale: **$3–$15 CPM** for an "Amazing Facts" audience. At 100K views/month → **$300–$1,500/month passively**.

---

## 🏗️ Architecture

```
GitHub Actions (daily cron 09:00 UTC)
        │
        ▼
  TopicAgent          ← Groq LLaMA 3.1 70B (free) + pytrends
        │
  ScriptAgent         ← Groq LLaMA 3.1 70B (free)
        │
  ┌─────┴──────┐
  │            │
ImageAgent  NarrationAgent
Pollinations  edge-tts
(free)        (free)
  │            │
  └─────┬──────┘
        │
  VideoAgent          ← moviepy + ffmpeg (open source)
        │
  SEOAgent            ← Groq LLaMA 3.1 70B (free)
        │
  YouTubePublisher    ← YouTube Data API v3 (free quota)
        │
  youtube.com/shorts/VIDEO_ID  💸
```

**Total running cost: $0/month** (all free tiers)

---

## 🚀 Quick Start (15 minutes)

### 1. Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/factsunlocked.git
cd factsunlocked
```

### 2. Run Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

### 3. Get Your Free Groq API Key

1. Go to **https://console.groq.com**
2. Sign up (free — no credit card)
3. Create an API key
4. Copy it

### 4. Set Up YouTube OAuth (one-time, ~5 minutes)

**A. Create Google Cloud project:**
1. Go to https://console.cloud.google.com/
2. Create a new project (e.g. "FactsUnlocked")
3. Navigate to **APIs & Services → Library**
4. Search and enable **YouTube Data API v3**
5. Go to **APIs & Services → Credentials**
6. Click **Create Credentials → OAuth 2.0 Client ID**
7. Application type: **Desktop app**
8. Download the JSON → save as `client_secrets.json` in the project root

**B. Authorise and get your refresh token:**
```bash
source .env
python scripts/get_youtube_token.py
```
The script opens your browser, you click Allow, and it prints three values.

### 5. Add GitHub Actions Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Where to get it |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com |
| `YOUTUBE_CLIENT_ID` | Printed by `get_youtube_token.py` |
| `YOUTUBE_CLIENT_SECRET` | Printed by `get_youtube_token.py` |
| `YOUTUBE_REFRESH_TOKEN` | Printed by `get_youtube_token.py` |

### 6. Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"**
3. Done ✅

The pipeline now runs automatically every day at 09:00 UTC.

---

## 🧪 Test Locally

```bash
# Load env vars
source .env

# Set Python path
export PYTHONPATH=$(pwd)/src

# Run the full pipeline
python src/main.py
```

You'll see step-by-step logs. The final video is saved to `workspace/<run_id>/final_video.mp4`.

---

## ⚙️ Configuration

Edit `config/settings.yaml` to customise:

```yaml
channel:
  niche: "amazing facts"      # Change to any niche
  language: "en-US"

video:
  scenes_count: 6             # Number of scenes (×~10s = video length)
  font_size: 72               # On-screen text size

tts:
  voice: "en-US-AriaNeural"  # TTS voice (see edge-tts docs for options)
```

### Available TTS Voices (free)

| Voice | Style |
|---|---|
| `en-US-AriaNeural` | Warm, natural female (default) |
| `en-US-GuyNeural` | Confident male |
| `en-GB-SoniaNeural` | British female — sounds authoritative |
| `en-AU-NatashaNeural` | Australian female |

---

## 📅 Posting Schedule

The cron in `.github/workflows/create_video.yml` defaults to **09:00 UTC daily**.

Change it by editing the cron expression:
```yaml
- cron: "0 9 * * *"     # Every day at 09:00 UTC
- cron: "0 9 * * 1-5"   # Weekdays only
- cron: "0 9,17 * * *"  # Twice daily (watch your YouTube quota!)
```

> **YouTube quota note:** Uploading costs 1,600 units. Free quota = 10,000/day → max **6 uploads/day**.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `GROQ_API_KEY` missing | Add secret in GitHub → Settings → Secrets |
| YouTube upload fails 403 | Re-run `get_youtube_token.py` to refresh credentials |
| Images too slow | Pollinations.ai can be slow — the 90s timeout handles it |
| Video has no audio | Check ffmpeg is installed: `ffmpeg -version` |
| Pipeline times out | Increase `timeout-minutes` in the workflow file |

---

## 📁 Project Structure

```
.
├── .github/
│   └── workflows/
│       └── create_video.yml      # Daily GitHub Actions workflow
├── src/
│   ├── main.py                   # Pipeline orchestrator
│   ├── agents/
│   │   ├── topic_agent.py        # Groq + pytrends topic research
│   │   ├── script_agent.py       # Groq script writer
│   │   ├── image_agent.py        # Pollinations.ai image gen
│   │   ├── narration_agent.py    # edge-tts TTS
│   │   ├── video_agent.py        # moviepy video assembly
│   │   └── seo_agent.py          # Groq SEO optimiser
│   ├── platforms/
│   │   └── youtube.py            # YouTube Data API v3 uploader
│   └── utils/
│       └── logger.py
├── config/
│   └── settings.yaml             # All tunable settings
├── scripts/
│   └── get_youtube_token.py      # One-time OAuth setup
├── requirements.txt
├── setup.sh
└── README.md
```

---

## 📈 Growth Tips

1. **Pick a sub-niche** — "Space facts", "History secrets", or "Body facts" outperform generic "Amazing facts"
2. **Consistency beats quality** — daily posting matters more than perfect videos early on
3. **Add affiliate links** from day 1 — Amazon Associates pays for clicks, not just sales
4. **Engage in comments** — even 10 min/week of replies accelerates growth
5. **Cross-post to TikTok manually** at first — 1080×1920 format is already optimised

---

## 📜 License

MIT — do whatever you want with this code.
