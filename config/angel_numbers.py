"""
angel_numbers.py — static numerology reference data.

Mirrors the structure of config/zodiac.py so the AngelNumbers channel can
plug into the exact same agent pipeline (ImageAgent, NarrationAgent,
VideoAgent, MusicAgent, ThumbnailAgent, YouTubePublisher) with zero changes
to any of those files.

No real-time computation is required for numerology (unlike astrology's
ephemeris), so there is no "engine" module — all data here is static and
fed straight into the script agent.
"""

# ── Number roster ──────────────────────────────────────────────────────────
# 12 sequences chosen to match the existing 12-per-day production rhythm
# (same daily volume as AstroFacts' 12 signs) and to cover the highest
# search-volume angel number queries.

ANGEL_NUMBERS = [
    "111", "222", "333", "444", "555",
    "666", "777", "888", "999",
    "1111", "1212", "000",
]

# ── Display symbol (kept simple — the number itself reads best on Shorts) ──

NUMBER_SYMBOLS = {n: "✨" for n in ANGEL_NUMBERS}

# ── Core vibration / theme keywords (the "what it means" anchor) ───────────

NUMBER_CORE_MEANING = {
    "111":  "new beginnings, manifestation, alignment with thought",
    "222":  "balance, partnership, trust in timing",
    "333":  "growth, creativity, support from spiritual guides",
    "444":  "protection, stability, angels confirming you're on the right path",
    "555":  "major change, transformation, letting go of the old",
    "666":  "rebalancing, material vs. spiritual focus, self-care",
    "777":  "luck, spiritual awakening, alignment rewarded",
    "888":  "abundance, financial flow, cycles completing",
    "999":  "endings, completion, closing a major chapter",
    "1111": "portal moment, synchronicity, powerful manifestation window",
    "1212": "evolution, stepping into a higher version of yourself",
    "000":  "infinite potential, a fresh page, oneness with source",
}

# ── Life domain each number is most associated with (used to vary scenes) ──

NUMBER_LIFE_DOMAIN = {
    "111": "mindset & intentions",
    "222": "relationships & partnerships",
    "333": "creativity & self-expression",
    "444": "stability & home life",
    "555": "career & life-direction change",
    "666": "wellbeing & work-life balance",
    "777": "spiritual growth & luck",
    "888": "money & abundance",
    "999": "closure & letting go",
    "1111": "manifestation & synchronicity",
    "1212": "personal evolution",
    "000": "new chapters & fresh starts",
}

# ── Brand colour per number (image prompt colour-grading hint + thumbnail) ──

NUMBER_COLORS = {
    "111":  "#FFD700",  "222":  "#87CEEB",  "333":  "#DA70D6",
    "444":  "#228B22",  "555":  "#FF8C00",  "666":  "#8FBC8F",
    "777":  "#9400D3",  "888":  "#FFD700",  "999":  "#8B0000",
    "1111": "#00CED1",  "1212": "#40E0D0",  "000":  "#FFFFFF",
}

# ── Numerology "root number" (digit sum, classic reduction) ────────────────
# Used as a small bonus fact the script can drop in for extra credibility.

NUMBER_ROOT = {
    "111": 3, "222": 6, "333": 9, "444": 3, "555": 6,
    "666": 9, "777": 3, "888": 6, "999": 9,
    "1111": 4, "1212": 6, "000": 0,
}

ROOT_NUMBER_THEMES = {
    0: "wholeness and unlimited potential",
    3: "creative self-expression and joy",
    4: "structure, discipline, and groundwork",
    6: "love, responsibility, and harmony",
    9: "completion, compassion, and humanitarian purpose",
}

# ── Where viewers typically see this number (used for relatable hooks) ──────

COMMON_SIGHTINGS = [
    "the clock", "a receipt total", "a license plate", "a phone notification",
    "a price tag", "a street address", "a flight number", "a song timestamp",
]
