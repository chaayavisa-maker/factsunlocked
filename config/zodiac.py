"""
zodiac.py — static astrology reference data.

Contains every piece of sign-level data that is FIXED (ruling planets,
modalities, house associations, etc.).  Dynamic planetary positions
(where planets actually are on a given date) live in
src/utils/astro_engine.py so they can be computed at runtime.
"""

# ── Sign roster ───────────────────────────────────────────────────────────────

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── Glyphs ────────────────────────────────────────────────────────────────────

SIGN_SYMBOLS = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
    "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
    "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
}

# ── Elements ──────────────────────────────────────────────────────────────────

SIGN_ELEMENTS = {
    "Aries": "Fire",    "Leo": "Fire",    "Sagittarius": "Fire",
    "Taurus": "Earth",  "Virgo": "Earth", "Capricorn": "Earth",
    "Gemini": "Air",    "Libra": "Air",   "Aquarius": "Air",
    "Cancer": "Water",  "Scorpio": "Water", "Pisces": "Water",
}

# ── Modalities ────────────────────────────────────────────────────────────────

SIGN_MODALITIES = {
    "Aries": "Cardinal",  "Cancer": "Cardinal",
    "Libra": "Cardinal",  "Capricorn": "Cardinal",
    "Taurus": "Fixed",    "Leo": "Fixed",
    "Scorpio": "Fixed",   "Aquarius": "Fixed",
    "Gemini": "Mutable",  "Virgo": "Mutable",
    "Sagittarius": "Mutable", "Pisces": "Mutable",
}

# ── Ruling planets (traditional + modern where applicable) ────────────────────

SIGN_RULERS = {
    "Aries":       {"traditional": "Mars",    "modern": "Mars"},
    "Taurus":      {"traditional": "Venus",   "modern": "Venus"},
    "Gemini":      {"traditional": "Mercury", "modern": "Mercury"},
    "Cancer":      {"traditional": "Moon",    "modern": "Moon"},
    "Leo":         {"traditional": "Sun",     "modern": "Sun"},
    "Virgo":       {"traditional": "Mercury", "modern": "Mercury"},
    "Libra":       {"traditional": "Venus",   "modern": "Venus"},
    "Scorpio":     {"traditional": "Mars",    "modern": "Pluto"},
    "Sagittarius": {"traditional": "Jupiter", "modern": "Jupiter"},
    "Capricorn":   {"traditional": "Saturn",  "modern": "Saturn"},
    "Aquarius":    {"traditional": "Saturn",  "modern": "Uranus"},
    "Pisces":      {"traditional": "Jupiter", "modern": "Neptune"},
}

# ── Natural house association ─────────────────────────────────────────────────

SIGN_NATURAL_HOUSE = {
    "Aries": 1, "Taurus": 2, "Gemini": 3, "Cancer": 4,
    "Leo": 5, "Virgo": 6, "Libra": 7, "Scorpio": 8,
    "Sagittarius": 9, "Capricorn": 10, "Aquarius": 11, "Pisces": 12,
}

# ── House themes (used in prompt context) ────────────────────────────────────

HOUSE_THEMES = {
    1:  "identity, appearance, new beginnings, self-expression",
    2:  "money, possessions, values, self-worth, material security",
    3:  "communication, siblings, short travel, learning, local community",
    4:  "home, family, roots, ancestry, inner emotional foundation",
    5:  "creativity, romance, children, pleasure, self-expression, play",
    6:  "health, daily routines, work, service, habits, wellness",
    7:  "partnerships, marriage, contracts, open enemies, cooperation",
    8:  "transformation, shared resources, sexuality, death, rebirth, inheritance",
    9:  "higher education, philosophy, long travel, spirituality, expansion",
    10: "career, reputation, public image, authority, ambition, legacy",
    11: "friendships, community, goals, hopes, humanitarian causes, groups",
    12: "spirituality, solitude, hidden enemies, karma, the subconscious",
}

# ── Planet keywords (what each planet governs thematically) ──────────────────

PLANET_THEMES = {
    "Sun":     "ego, vitality, core identity, life purpose, confidence",
    "Moon":    "emotions, intuition, home, habits, subconscious needs",
    "Mercury": "communication, intellect, contracts, travel, logic, trade",
    "Venus":   "love, beauty, harmony, pleasure, finances, aesthetics",
    "Mars":    "drive, ambition, conflict, courage, sexuality, energy",
    "Jupiter": "expansion, luck, abundance, wisdom, faith, opportunity",
    "Saturn":  "discipline, restriction, karma, structure, lessons, time",
    "Uranus":  "sudden change, innovation, rebellion, liberation, technology",
    "Neptune": "dreams, illusion, spirituality, compassion, confusion, art",
    "Pluto":   "transformation, power, death/rebirth, obsession, evolution",
    "Chiron":  "healing, wounds, vulnerability turned to wisdom",
    "North Node": "destiny, soul growth, karmic direction",
    "South Node":  "past patterns, innate talents, comfort zone",
}

# ── Aspect meanings ───────────────────────────────────────────────────────────

ASPECT_MEANINGS = {
    "conjunction": "merging, intensification, new cycle beginning",
    "opposition":  "tension, awareness, balance needed between two areas",
    "trine":       "flow, ease, natural talent, opportunity, harmony",
    "square":      "friction, challenge, growth through overcoming obstacles",
    "sextile":     "opportunity, support, gentle positive energy",
    "quincunx":    "adjustment, awkward energy requiring flexibility",
}

# ── Brand colours (for image prompt colour grading hints) ────────────────────

SIGN_COLORS = {
    "Aries": "#FF4500",      "Taurus": "#228B22",
    "Gemini": "#FFD700",     "Cancer": "#87CEEB",
    "Leo": "#FF8C00",        "Virgo": "#8FBC8F",
    "Libra": "#DDA0DD",      "Scorpio": "#8B0000",
    "Sagittarius": "#9400D3","Capricorn": "#2F4F4F",
    "Aquarius": "#00CED1",   "Pisces": "#40E0D0",
}

# ── Exaltation / detriment / fall (dignity table) ───────────────────────────

PLANET_DIGNITY = {
    # planet: {exaltation_sign, detriment_signs, fall_sign}
    "Sun":     {"exaltation": "Aries",       "detriment": ["Aquarius"],         "fall": "Libra"},
    "Moon":    {"exaltation": "Taurus",      "detriment": ["Capricorn"],        "fall": "Scorpio"},
    "Mercury": {"exaltation": "Virgo",       "detriment": ["Sagittarius","Pisces"], "fall": "Pisces"},
    "Venus":   {"exaltation": "Pisces",      "detriment": ["Aries","Scorpio"],  "fall": "Virgo"},
    "Mars":    {"exaltation": "Capricorn",   "detriment": ["Taurus","Libra"],   "fall": "Cancer"},
    "Jupiter": {"exaltation": "Cancer",      "detriment": ["Gemini","Virgo"],   "fall": "Capricorn"},
    "Saturn":  {"exaltation": "Libra",       "detriment": ["Cancer","Leo"],     "fall": "Aries"},
    "Uranus":  {"exaltation": "Scorpio",     "detriment": ["Leo"],              "fall": "Taurus"},
    "Neptune": {"exaltation": "Cancer",      "detriment": ["Virgo"],            "fall": "Capricorn"},
    "Pluto":   {"exaltation": "Aries",       "detriment": ["Taurus"],           "fall": "Libra"},
}
