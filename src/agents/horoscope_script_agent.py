"""
HoroscopeScriptAgent
─────────────────────
Generates horoscope video scripts grounded in REAL planetary positions.

Pipeline per call:
  1. astro_engine.get_planetary_context()  → live sky positions for the date
  2. astro_engine.get_sign_transits()      → sign-specific interpretation data
  3. build a richly-detailed prompt        → sent to Groq
  4. parse and return structured JSON

The image_agent, narration_agent, and video_agent are intentionally
NOT touched by this file.
"""

import json
import re
from datetime import date

from src.utils.groq_client import call_groq
from src.utils.astro_engine import get_planetary_context, get_sign_transits
from src.utils.logger import get_logger
from config.zodiac import (
    SIGN_ELEMENTS, SIGN_MODALITIES, SIGN_RULERS,
    SIGN_NATURAL_HOUSE, HOUSE_THEMES,
    SIGN_SYMBOLS, PLANET_THEMES, ASPECT_MEANINGS,
)

logger = get_logger(__name__)

# Scenes per period (keeps video lengths sensible)
PERIOD_SCENES = {
    "daily":   5,
    "weekly":  6,
    "monthly": 7,
    "yearly":  8,
}

# Period label used in narration
PERIOD_LABEL = {
    "daily":   "today",
    "weekly":  "this week",
    "monthly": "this month",
    "yearly":  "this year",
}

# How far ahead each period looks (affects ingress scanning)
PERIOD_HORIZON = {
    "daily":   "the next 24 hours",
    "weekly":  "the next 7 days",
    "monthly": "the coming month",
    "yearly":  "the full year ahead",
}


def _build_astro_brief(sign: str, period: str, ctx: dict, transits: dict) -> str:
    """
    Assemble a structured plain-text astronomy brief that gets injected
    verbatim into the Groq prompt as the factual foundation.
    """
    today       = ctx["reference_date"]
    period_end  = ctx["period_end"]
    ruler_trad  = transits["ruler_trad"]
    ruler_mod   = transits["ruler_mod"]
    element     = SIGN_ELEMENTS[sign]
    modality    = SIGN_MODALITIES[sign]
    house       = transits["house"]
    house_theme = transits["house_theme"]
    symbol      = SIGN_SYMBOLS[sign]

    # Relevant aspects: those involving this sign's ruling planet or
    # planets transiting the sign
    focal_planets = set([ruler_trad, ruler_mod] + transits["in_sign"])
    relevant_aspects = [
        asp for asp in ctx["aspects"]
        if asp["planet1"] in focal_planets or asp["planet2"] in focal_planets
    ]
    aspect_block = "\n".join(
        f"  • {a['planet1']} {a['aspect']} {a['planet2']}"
        f" — {ASPECT_MEANINGS.get(a['aspect'], '')} "
        f"(orb {a['orb']}°, {'applying ↗' if a['applying'] else 'separating ↘'})"
        for a in relevant_aspects
    ) or "  No major aspects involving ruling planets within orb"

    brief = f"""
═══════════════════════════════════════════════════════════════
REAL ASTRONOMICAL DATA — {sign.upper()} {symbol}  |  {period.upper()}
Reference date: {today}  →  Period ends: {period_end}
═══════════════════════════════════════════════════════════════

SIGN PROFILE
  Element:   {element}
  Modality:  {modality}
  Natural House: {house}th — governs {house_theme}
  Traditional ruler: {ruler_trad}
  Modern ruler: {ruler_mod}

RULING PLANET STATUS
  {transits['ruler_text']}

PLANETS CURRENTLY IN {sign.upper()}
  {transits['planets_in_sign_text']}

PLANETS ENTERING {sign.upper()} DURING THIS PERIOD
  {transits['arriving_text']}

SUPPORTIVE ENERGIES (trine signs — flow and ease)
  {transits['trining_text']}

TENSION POINTS (square signs — growth through friction)
  {transits['squaring_text']}

OPPOSITION AXIS (awareness and balance)
  Opposite sign: {ZODIAC_SIGNS_OPP(sign)} | Planets there: {transits['opposing_text']}

ACTIVE ASPECTS INVOLVING {sign.upper()}'S RULERS
{aspect_block}

CURRENT SKY AT A GLANCE
  Moon: {ctx['moon_phase']} in {ctx['moon_sign']}
  North Node: {ctx['north_node_sign']} (South Node: {ctx['south_node_sign']})
  Active retrogrades: {ctx['retrogrades_text']}

ALL PLANET POSITIONS
{ctx['positions_text']}

ALL INGRESSES THIS PERIOD
{ctx['ingresses_text']}
═══════════════════════════════════════════════════════════════
""".strip()
    return brief


def ZODIAC_SIGNS_OPP(sign: str) -> str:
    from config.zodiac import ZODIAC_SIGNS
    idx = ZODIAC_SIGNS.index(sign)
    return ZODIAC_SIGNS[(idx + 6) % 12]


def generate_horoscope_script(
    sign: str,
    period: str,
    api_key_env: str = "GROQ_API_KEY_ASTRO",
    reference_date: date = None,
) -> dict:
    """
    Generate a horoscope video script grounded in real planetary positions.

    Returns a dict:
        title, hook, scenes [{narration, image_prompt}], closing_cta,
        description, tags
    """
    today        = reference_date or date.today()
    scenes_count = PERIOD_SCENES.get(period, 5)
    label        = PERIOD_LABEL.get(period, "today")
    horizon      = PERIOD_HORIZON.get(period, "the coming period")
    element      = SIGN_ELEMENTS[sign]
    ruler        = SIGN_RULERS[sign]["traditional"]
    symbol       = SIGN_SYMBOLS[sign]
    house        = SIGN_NATURAL_HOUSE[sign]
    house_theme  = HOUSE_THEMES[house]
    planet_theme = PLANET_THEMES.get(ruler, "")

    # ── 1. Compute real sky positions ────────────────────────────────────────
    logger.info(f"Computing planetary positions for {sign} {period} ({today})")
    try:
        ctx      = get_planetary_context(period, today)
        transits = get_sign_transits(sign, ctx)
        astro_brief = _build_astro_brief(sign, period, ctx, transits)
        logger.info(f"Planetary brief ready — {len(ctx['aspects'])} aspects found")
    except Exception as e:
        logger.warning(f"Astro engine error: {e} — falling back to minimal context")
        astro_brief = f"Date: {today.isoformat()}\nSign: {sign} ({element}, ruled by {ruler})"
        transits = {}
        ctx = {}

    # ── 2. Build the Groq prompt ─────────────────────────────────────────────
    system_prompt = (
        "You are a professional Western astrologer with 20 years of experience "
        "and a compelling YouTube presence. You interpret horoscopes using REAL "
        "planetary transits, aspects, and traditional astrological technique. "
        "Your readings are specific, accurate, and empowering — never vague. "
        "You always ground every prediction in the actual planetary data given to you. "
        "Return ONLY valid JSON — no markdown fences, no preamble, no extra text."
    )

    # Ruler retrograde flag for extra emphasis
    ruler_rx_note = ""
    if transits.get("ruler_retrograde"):
        ruler_rx_note = (
            f"\n  ⚠️  IMPORTANT: {ruler} (ruling planet of {sign}) is RETROGRADE. "
            f"This is a major theme — the script MUST address what this means for {sign}: "
            f"review, revision, delays, and internal focus in matters of {planet_theme}."
        )

    # Moon phase note
    moon_note = ""
    moon_phase = ctx.get("moon_phase", "")
    if moon_phase in ("New Moon", "Full Moon"):
        moon_sign_val = ctx.get("moon_sign", "")
        moon_note = (
            f"\n  ⚠️  {moon_phase} in {moon_sign_val} is active — this is a peak "
            f"lunar energy moment. The script MUST weave this in as a significant event."
        )

    # Ingress emphasis
    ingress_note = ""
    if transits.get("arriving"):
        ingress_note = (
            f"\n  📌 The following planets enter {sign} during this period — "
            f"these arrivals are major story beats: "
            + ", ".join(transits["arriving"])
        )

    user_prompt = f"""
You are writing a {period} horoscope video script for {sign} {symbol}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REAL PLANETARY DATA YOU MUST USE (computed live from the ephemeris):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{astro_brief}
{ruler_rx_note}{moon_note}{ingress_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASTROLOGICAL INTERPRETATION RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Every statement must be justified by a specific planet, aspect, or transit
  from the data above. Never make up planetary positions.
• Translate technical astrology into clear, relatable life guidance:
  — Love & relationships: Venus, 7th house, 5th house aspects
  — Career & money: Saturn, Jupiter, 10th house, 2nd house
  — Health & daily life: 6th house, Mars, Virgo transits
  — Communication & travel: Mercury, 3rd house, 9th house
  — Inner growth: Moon phase, 12th house, Pluto/Neptune transits
• Reference actual degree positions or aspect names when relevant (e.g.
  "With Jupiter trine your ruling Venus..." or "Mercury's station direct this
  week lifts communication blocks...").
• {sign} is a {element} sign of {SIGN_MODALITIES[sign]} quality, naturally
  governing the {house}th house ({house_theme}).
• Tone: authoritative yet warm, specific yet uplifting. 
  Never doom & gloom — even squares and retrogrades are growth opportunities.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (JSON, exactly {scenes_count} scenes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "title": "YouTube Short title ≤60 chars — include {sign}, period, and a specific hook word",
  "hook": "One electric opening sentence referencing a specific transit (spoken in 3 seconds)",
  "scenes": [
    {{
      "narration": "Spoken narration for this scene, 35-45 words. Must reference specific planetary data.",
      "image_prompt": "Vivid image generation prompt — cosmic, ethereal, portrait orientation, NO text in image, colour palette matching {element} energy. Describe mood, lighting, celestial elements."
    }}
  ],
  "closing_cta": "Subscribe + like call-to-action, 1 sentence, mention horoscope frequency",
  "description": "YouTube/TikTok description 200-250 chars, include date reference {today.strftime('%B %Y')}, emojis, sign, period",
  "tags": ["list of exactly 15 SEO tags as strings"]
}}

Scene allocation guidance for {scenes_count} scenes:
  Scene 1 — Opening: hook + most important transit or ruler status for {label}
  Scene 2 — Love & relationships angle (Venus/7th house data)
  Scene 3 — Career & finances angle (Saturn/Jupiter/10th house data)
  Scene 4 — Personal growth & wellbeing (Moon phase + inner planet aspects)
{"  Scene 5 — Week summary + lucky timing windows" if scenes_count >= 5 else ""}
{"  Scene 6 — Deeper spiritual or karmic theme (nodes, outer planets)" if scenes_count >= 6 else ""}
{"  Scene 7 — Month's standout peak moment (ingress or station)" if scenes_count >= 7 else ""}
{"  Scene 8 — Year-ahead overview and major Jupiter/Saturn cycles" if scenes_count >= 8 else ""}
  Final scene — Closing affirmation grounded in {sign}'s {element} element strengths
"""

    logger.info(f"Calling Groq for {sign} {period} script…")
    raw = call_groq(
        prompt=user_prompt,
        system=system_prompt,
        temperature=0.75,   # slightly lower for factual grounding
        max_tokens=2000,
        api_key_env=api_key_env,
    )

    # ── 3. Parse JSON ────────────────────────────────────────────────────────
    try:
        script = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            script = json.loads(match.group())
        else:
            raise ValueError(
                f"Groq returned non-JSON for {sign} {period}:\n{raw[:300]}"
            )

    # Validate scene count (pad or trim gracefully)
    scenes = script.get("scenes", [])
    if len(scenes) < scenes_count:
        logger.warning(
            f"Groq returned {len(scenes)} scenes, expected {scenes_count} — padding"
        )
        while len(scenes) < scenes_count:
            scenes.append({
                "narration": f"The stars are aligned in your favour, {sign}. Trust the journey.",
                "image_prompt": f"cosmic nebula in {SIGN_ELEMENTS[sign]} colours, ethereal and mystical, portrait",
            })
        script["scenes"] = scenes
    elif len(scenes) > scenes_count:
        script["scenes"] = scenes[:scenes_count]

    logger.info(f"Script ready: '{script.get('title', '?')}'")
    return script


def generate_seo_metadata(
    sign: str,
    period: str,
    script: dict,
    api_key_env: str = "GROQ_API_KEY_ASTRO",
) -> dict:
    """
    Optimise YouTube/TikTok metadata.
    Called separately so the Groq budget is split cleanly.
    """
    today_str  = date.today().strftime("%B %d, %Y")
    month_year = date.today().strftime("%B %Y")
    year       = date.today().year
    ruler      = SIGN_RULERS[sign]["traditional"]
    element    = SIGN_ELEMENTS[sign]
    symbol     = SIGN_SYMBOLS[sign]

    system = (
        "You are an expert YouTube SEO specialist who also understands astrology. "
        "Return ONLY valid JSON — no markdown fences, no extra text."
    )

    prompt = f"""
Optimise YouTube metadata for this {period} horoscope video.

Sign:   {sign} {symbol}
Period: {period}
Date:   {today_str}

Draft title:       {script.get('title', '')}
Draft description: {script.get('description', '')}
Script hook:       {script.get('hook', '')}
Ruling planet:     {ruler}
Element:           {element}

Return JSON:
{{
  "title": "final title ≤60 chars — must include {sign}, {period}, and {month_year}",
  "description": "Full description 500-800 chars. Include: date '{today_str}', sign {sign}, ruler {ruler}, element {element}, 3-4 relevant life areas covered, CTA to subscribe, hashtags on last line",
  "tags": ["exactly 20 SEO tag strings — mix of: sign name, '{sign} horoscope', '{period} horoscope {year}', ruling planet, element, life areas (love, career, money, health), astrology terms"]
}}
"""
    raw = call_groq(prompt, system=system, max_tokens=900, api_key_env=api_key_env)
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    # Graceful fallback
    return {
        "title":       script.get("title", f"{sign} {period.title()} Horoscope {month_year}"),
        "description": script.get("description", ""),
        "tags":        script.get("tags", []),
    }
