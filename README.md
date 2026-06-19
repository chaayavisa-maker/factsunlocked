# 🎬 FactsUnlocked + 🔮 AstroFacts — Autonomous YouTube & TikTok Video Business

> Two fully automated pipelines that research topics / generate horoscopes, write scripts,
> produce vertical videos, and publish to YouTube and TikTok — **every single day** — without
> touching anything after setup.

---

## 📦 Channels

| Channel | Niche | Platforms | Frequency | Groq Key |
|---|---|---|---|---|
| **FactsUnlocked** | Amazing Facts | YouTube Shorts | 1 video/day | `GROQ_API_KEY` |
| **AstroFacts** | Horoscopes | YouTube Shorts + TikTok | 12 daily + weekly + monthly + yearly | `GROQ_API_KEY_ASTRO` |
| **AngelNumbers** *(new)* | Angel numbers / numerology | YouTube Shorts + TikTok | 12 daily | `GROQ_API_KEY_ANGEL` |

AngelNumbers publishes **one video per recurring number sequence** (111, 222, 333 … 1111, 1212, 000) every day — the same 12-per-batch rhythm as AstroFacts, reusing every shared agent (images, narration, video, music, thumbnails) untouched. See `src/angelnumbers_main.py` and `config/angel_numbers.py`.

AstroFacts publishes **one video per zodiac sign** per period — 12 daily, 12 weekly, 12 monthly, and 12 on Jan 1st.

---

## 🏗️ Architecture

```
GitHub Actions (scheduled crons)
        │
        ├── factsunlocked_daily.yml  ──▶  src/main.py
        │                                  └── TopicAgent (GROQ_API_KEY)
        │                                  └── ScriptAgent
        │                                  └── ImageAgent (Pollinations)
        │                                  └── NarrationAgent (edge-tts)
        │                                  └── VideoAgent (moviepy)
        │                                  └── YouTubePublisher
        │
        └── astrofacts_daily.yml     ──▶  src/astrofacts_main.py --period daily
            astrofacts_weekly.yml         └── HoroscopeScriptAgent (GROQ_API_KEY_ASTRO)
            astrofacts_monthly.yml        └── ImageAgent (Pollinations)
            astrofacts_yearly.yml         └── NarrationAgent (edge-tts)
                                          └── VideoAgent (moviepy)
                                          └── YouTubePublisher (_ASTRO credentials)
                                          └── TikTokPublisher (_ASTRO credentials)
```

**Total running cost: $0/month** (all free tiers)

---

## 🚀 Setup

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/factsunlocked.git
cd factsunlocked
chmod +x setup.sh && ./setup.sh
```

### 2. Get Groq API Keys (two accounts = two keys = no rate-limit sharing)

| Key | Used by | Get at |
|---|---|---|
| `GROQ_API_KEY` | FactsUnlocked | https://console.groq.com |
| `GROQ_API_KEY_ASTRO` | AstroFacts | https://console.groq.com (second account or key) |

### 3. Set up YouTube for FactsUnlocked (original channel)

```bash
python scripts/get_youtube_token.py
```

Add secrets: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`

### 4. Set up YouTube for AstroFacts (new channel)

1. Create a **separate Google Cloud project** for AstroFacts
2. Enable YouTube Data API v3, create OAuth credentials → save as `client_secrets_astro.json`
3. Run:

```bash
python scripts/get_astro_youtube_token.py
```

Add secrets: `YOUTUBE_CLIENT_ID_ASTRO`, `YOUTUBE_CLIENT_SECRET_ASTRO`, `YOUTUBE_REFRESH_TOKEN_ASTRO`

4. Create 4 YouTube playlists on the AstroFacts channel (Daily / Weekly / Monthly / Yearly)
5. Paste their IDs into `config/settings.yaml` under `astrofacts.platforms.youtube.playlist_ids`

### 5. Set up TikTok for AstroFacts

1. Apply at https://developers.tiktok.com → create app → enable **Content Posting API**
2. Set redirect URI: `http://localhost:8080/callback`
3. Set env vars locally, then run:

```bash
TIKTOK_CLIENT_KEY_ASTRO=xxx TIKTOK_CLIENT_SECRET_ASTRO=yyy python scripts/get_tiktok_token.py
```

Add secrets: `TIKTOK_CLIENT_KEY_ASTRO`, `TIKTOK_CLIENT_SECRET_ASTRO`, `TIKTOK_REFRESH_TOKEN_ASTRO`

### 6. Add all GitHub Actions Secrets

Go to repo → **Settings → Secrets and variables → Actions**

| Secret | Channel |
|---|---|
| `GROQ_API_KEY` | FactsUnlocked |
| `YOUTUBE_CLIENT_ID` | FactsUnlocked |
| `YOUTUBE_CLIENT_SECRET` | FactsUnlocked |
| `YOUTUBE_REFRESH_TOKEN` | FactsUnlocked |
| `GROQ_API_KEY_ASTRO` | AstroFacts |
| `YOUTUBE_CLIENT_ID_ASTRO` | AstroFacts |
| `YOUTUBE_CLIENT_SECRET_ASTRO` | AstroFacts |
| `YOUTUBE_REFRESH_TOKEN_ASTRO` | AstroFacts |
| `TIKTOK_CLIENT_KEY_ASTRO` | AstroFacts |
| `TIKTOK_CLIENT_SECRET_ASTRO` | AstroFacts |
| `TIKTOK_REFRESH_TOKEN_ASTRO` | AstroFacts |

### 7. Enable GitHub Actions

Repo → **Actions** tab → enable workflows ✅

---

## 📅 Posting Schedule

| Workflow | Cron | Content |
|---|---|---|
| `factsunlocked_daily.yml` | `0 9 * * *` | 1 facts video |
| `astrofacts_daily.yml` | `0 6 * * *` | 12 daily horoscopes |
| `astrofacts_weekly.yml` | `0 7 * * 1` | 12 weekly horoscopes (Monday) |
| `astrofacts_monthly.yml` | `0 8 1 * *` | 12 monthly horoscopes (1st of month) |
| `astrofacts_yearly.yml` | `0 8 1 1 *` | 12 yearly horoscopes (Jan 1st) |

> **YouTube quota note:** Uploading = 1,600 units. Free quota = 10,000/day → max 6 uploads/day.
> AstroFacts uses a **separate Google Cloud project** so its quota is independent.

---

## 🧪 Test Locally

```bash
export PYTHONPATH=$(pwd)

# Test FactsUnlocked
python src/main.py

# Test AstroFacts daily (all signs)
python src/astrofacts_main.py --period daily

# Test a single sign
python src/astrofacts_main.py --period daily --sign Aries

# Test other periods
python src/astrofacts_main.py --period weekly
python src/astrofacts_main.py --period monthly
python src/astrofacts_main.py --period yearly
```

---

## 📁 Project Structure

```
.
├── .github/workflows/
│   ├── factsunlocked_daily.yml     # FactsUnlocked: 1 video/day
│   ├── astrofacts_daily.yml        # AstroFacts: 12 daily horoscopes
│   ├── astrofacts_weekly.yml       # AstroFacts: 12 weekly horoscopes
│   ├── astrofacts_monthly.yml      # AstroFacts: 12 monthly horoscopes
│   └── astrofacts_yearly.yml       # AstroFacts: 12 yearly horoscopes
├── src/
│   ├── main.py                     # FactsUnlocked pipeline
│   ├── astrofacts_main.py          # AstroFacts pipeline (all signs × period)
│   ├── agents/
│   │   ├── horoscope_script_agent.py  # Zodiac-aware script + SEO generator
│   │   ├── image_agent.py             # Pollinations.ai image generation
│   │   ├── narration_agent.py         # edge-tts TTS
│   │   └── video_agent.py             # moviepy video assembly
│   ├── platforms/
│   │   ├── youtube.py              # YouTube uploader (supports playlists)
│   │   └── tiktok.py               # TikTok Content Posting API uploader
│   └── utils/
│       ├── groq_client.py          # Groq REST wrapper (picks key by env var)
│       └── logger.py
├── config/
│   ├── settings.yaml               # All settings for both channels
│   └── zodiac.py                   # Zodiac sign data (names, symbols, colours)
├── scripts/
│   ├── get_youtube_token.py        # OAuth for FactsUnlocked YouTube
│   ├── get_astro_youtube_token.py  # OAuth for AstroFacts YouTube
│   └── get_tiktok_token.py         # OAuth for AstroFacts TikTok
├── requirements.txt
└── setup.sh
```

---

## ⚙️ Configuration

Edit `config/settings.yaml` to customise voices, video settings, and toggle platforms:

```yaml
astrofacts:
  platforms:
    tiktok:
      enabled: true   # set false to disable TikTok
    youtube:
      playlist_ids:
        daily: "PLxxx"   # paste your playlist IDs here
```

---

## 📜 License

MIT
