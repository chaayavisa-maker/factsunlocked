"""
MoonScriptAgent — generates scripts for the "Moon & Stars Weekly" extension.

This is a NEW content type on astrounlocked focused on:
  - Weekly Moon phase energy (New Moon, Waxing, Full Moon, Waning)
  - Collective (not sign-specific) cosmic weather
  - Short motivational / manifestation angle

Why this works for growth:
  - Moon content is searched 3-5× more than individual sign horoscopes
  - "Full Moon in [sign]" spikes algorithmically every ~28 days
  - Collective content gets shared by ALL 12 signs → 12× audience reach
  - Moon = manifestation = high-engagement audience (comments, saves)
"""

import json
import re
from datetime import date, timedelta

from src.utils.groq_client import call_groq
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Moon phase cycle (simplified — 29.5-day synodic month)
MOON_PHASES = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
               "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]

MOON_THEMES = {
    "New Moon":        {"energy": "new beginnings, intention-setting, planting seeds", "emoji": "🌑"},
    "Waxing Crescent": {"energy": "building momentum, taking first steps, nurturing plans", "emoji": "🌒"},
    "First Quarter":   {"energy": "overcoming challenges, decision points, pushing forward", "emoji": "🌓"},
    "Waxing Gibbous":  {"energy": "refining, adjusting, almost there — trust the process", "emoji": "🌔"},
    "Full Moon":       {"energy": "peak manifestation, release, emotional clarity, celebration", "emoji": "🌕"},
    "Waning Gibbous":  {"energy": "gratitude, sharing wisdom, distributing what you've built", "emoji": "🌖"},
    "Last Quarter":    {"energy": "releasing what no longer serves, forgiveness, letting go", "emoji": "🌗"},
    "Waning Crescent": {"energy": "rest, reflection, surrender, preparing for the new cycle", "emoji": "🌘"},
}


def _estimate_moon_phase(for_date: date) -> str:
    """
    Rough moon phase estimate based on a known New Moon anchor.
    For production, swap this with ephem or astropy for exact phase.
    Known New Moon anchor: 2024-01-11
    """
    anchor = date(2024, 1, 11)
    days_since = (for_date - anchor).days % 30
    phase_index = int((days_since / 30) * 8) % 8
    return MOON_PHASES[phase_index]


def generate_moon_script(
    for_date: date,
    api_key_env: str = "GROQ_API_KEY_ASTRO",
    moon_phase: str = None,
) -> dict:
    """
    Generate a collective weekly Moon energy script.
    Returns a dict compatible with the existing video pipeline.
    """
    if moon_phase is None:
        moon_phase = _estimate_moon_phase(for_date)

    theme = MOON_THEMES.get(moon_phase, MOON_THEMES["Full Moon"])
    emoji = theme["emoji"]
    energy = theme["energy"]

    prompt = f"""You are an expert astrologer creating a short, HIGH-ENERGY YouTube Shorts script.

Topic: {emoji} {moon_phase} — collective weekly cosmic energy
Date: {for_date.isoformat()}
Moon phase energy: {energy}

Write a 5-scene horoscope video script with this EXACT JSON structure:
{{
  "hook": "One electrifying opening sentence (max 12 words, starts with the moon phase name)",
  "scenes": [
    {{
      "narration": "35-50 word narration for this scene",
      "caption": "Max 6 words for on-screen caption",
      "image_prompt": "Vivid image generation prompt for this scene"
    }}
  ],
  "closing_cta": "Subscribe + follow for daily cosmic updates!"
}}

Rules:
- Scene 1: What the {moon_phase} means energetically this week (universal)
- Scene 2: Love & relationships — what the moon activates
- Scene 3: Career & abundance — cosmic opportunities
- Scene 4: Health & energy — what to prioritise
- Scene 5: Manifestation ritual or affirmation for this moon phase
- Tone: mystical, empowering, personal — speak directly to "you"
- Each scene narration must be self-contained and punchy
- End every scene with forward momentum, never doom and gloom
- NAME LIMIT: say "{moon_phase}" out loud at most twice across the hook + 5 scenes combined —
  everywhere else say "this phase" / "this energy" or just speak directly to "you"
- Return ONLY the JSON, no preamble, no markdown fences"""

    raw = call_groq(prompt, api_key_env=api_key_env)

    try:
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        script = json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON parse failed ({e}), using fallback structure")
        script = {
            "hook": f"{emoji} The {moon_phase} is here — and everything is about to shift.",
            "scenes": [
                {
                    "narration": f"The {moon_phase} arrives this week, flooding us with {energy}. This is a powerful portal.",
                    "caption": f"{moon_phase} Energy",
                    "image_prompt": f"mystical {moon_phase.lower()}, cosmic energy, ethereal glow, deep space",
                },
            ],
            "closing_cta": "Subscribe for weekly moon energy updates!",
        }

    # Ensure required keys
    script.setdefault("payoff", script.get("closing_cta", ""))
    script.setdefault("outro", "Subscribe for your weekly moon energy reading!")

    # Build image queries for ImageAgent
    script["image_queries"] = (
        [f"{moon_phase} glowing in night sky, cosmic mystical, deep space, ethereal light, 8K portrait"]
        + [s.get("image_prompt", f"cosmic {moon_phase.lower()} energy, mystical, ethereal")
           for s in script.get("scenes", [])]
        + ["moon goddess divine feminine energy, celestial light, stars, cosmic, mystical portrait"]
    )

    script["moon_phase"] = moon_phase
    script["moon_emoji"] = emoji
    script["for_date"]   = for_date.isoformat()

    logger.info(f"🌕 Moon script generated: {moon_phase} for {for_date}")
    return script


def generate_moon_seo(moon_phase: str, script: dict, api_key_env: str = "GROQ_API_KEY_ASTRO") -> dict:
    """Generate SEO metadata for a Moon energy video."""
    emoji = MOON_THEMES.get(moon_phase, {}).get("emoji", "🌕")
    hook  = script.get("hook", f"{moon_phase} energy this week")

    prompt = f"""Generate YouTube SEO metadata for a Moon energy video.

Moon Phase: {moon_phase}
Hook: {hook}

Return ONLY this JSON (no markdown):
{{
  "title": "SEO title max 70 chars, include moon phase name and current year",
  "description": "150-200 word description, include moon phase, manifestation, weekly energy keywords",
  "tags": ["list", "of", "15", "relevant", "tags"]
}}"""

    raw = call_groq(prompt, api_key_env=api_key_env)
    try:
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        return json.loads(clean)
    except Exception:
        return {
            "title": f"{emoji} {moon_phase} Weekly Energy — What The Stars Are Saying",
            "description": f"This week's {moon_phase} brings powerful energy for transformation. "
                           "Tune in to your weekly cosmic weather forecast and learn how to harness "
                           f"the {moon_phase} energy for love, career, and manifestation. "
                           "Subscribe for weekly moon readings and daily horoscopes.",
            "tags": [moon_phase, "moon phase", "weekly horoscope", "manifestation",
                     "astrology", "cosmic energy", "full moon", "new moon",
                     "moon reading", "spiritual", "law of attraction",
                     "weekly energy", "astrology 2026", "moon magic", "horoscope"],
        }
