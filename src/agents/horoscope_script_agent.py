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

# ── Period configuration ──────────────────────────────────────────────────────

# Scenes per period (keeps video lengths sensible but scales with depth needed)
PERIOD_SCENES = {
    "daily":   5,
    "weekly":  6,
    "monthly": 7,
    "yearly":  8,
}

# How to refer to the period IN the content (from the audience's perspective).
# Always forward-looking since we generate one period ahead of the run date.
PERIOD_LABEL = {
    "daily":   "tomorrow",
    "weekly":  "next week",
    "monthly": "next month",
    "yearly":  "next year",
}

# Narration word count per scene, scaled to how much a period needs to cover.
# Daily shorts are tight; yearly readings need room to map out 12 months.
PERIOD_NARRATION_WORDS = {
    "daily":   "35-45",
    "weekly":  "45-55",
    "monthly": "55-65",
    "yearly":  "65-80",
}

# How far ahead each period looks (affects ingress scanning in the astro engine)
PERIOD_HORIZON = {
    "daily":   "the next 24 hours",
    "weekly":  "the next 7 days",
    "monthly": "the coming month",
    "yearly":  "the full year ahead",
}

# Human-readable span description used in prompts
PERIOD_SPAN = {
    "daily":   "a single day",
    "weekly":  "a full 7-day week",
    "monthly": "a full calendar month",
    "yearly":  "a full 12-month year",
}

# Per-period scene allocation guidance injected into the prompt.
# Each map is tailored so the LLM knows exactly what temporal scope each
# scene must cover — prevents a monthly/yearly script from thinking in
# daily or weekly terms.
PERIOD_SCENE_GUIDE = {
    "daily": """\
  Scene 1 — Opening: hook + the single most important transit or aspect for tomorrow
  Scene 2 — Love & relationships: Venus/7th house data for the day
  Scene 3 — Career & finances: Saturn/Jupiter/10th house for the day
  Scene 4 — Personal growth & wellbeing: Moon phase + inner planet aspects
  Scene 5 — Closing affirmation grounded in {sign}'s {element} strengths""",

    "weekly": """\
  Scene 1 — Opening: hook + the dominant transit or aspect shaping the whole week
  Scene 2 — Early-week energy (Mon–Wed): key planetary ingress or aspect
  Scene 3 — Love & relationships this week: Venus/7th house data
  Scene 4 — Career & finances this week: Saturn/Jupiter/10th house data
  Scene 5 — Peak moment or turning point mid-to-late week: station, ingress, or exact aspect
  Scene 6 — Closing affirmation and weekend outlook, grounded in {sign}'s {element} strengths""",

    "monthly": """\
  Scene 1 — Opening: hook + the defining planetary story arc for the whole month
  Scene 2 — First half of the month (weeks 1-2): key ingresses, aspects, or stations
  Scene 3 — Second half of the month (weeks 3-4): how energy shifts, what builds or resolves
  Scene 4 — Love & relationships this month: Venus/7th house arc across the month
  Scene 5 — Career & finances this month: Saturn/Jupiter/10th house developments
  Scene 6 — Standout peak moment: the single most important day or transit of the month
  Scene 7 — Closing affirmation: month's overarching theme, grounded in {sign}'s {element} strengths""",

    "yearly": """\
  Scene 1 — Opening: hook + the single biggest planetary shift defining {sign}'s whole year
  Scene 2 — Q1 (Jan–Mar): which themes open the year, what seeds to plant
  Scene 3 — Q2 (Apr–Jun): how energy accelerates or shifts, key mid-year transits
  Scene 4 — Q3 (Jul–Sep): the year's peak zone — major conjunctions, oppositions, or stations
  Scene 5 — Q4 (Oct–Dec): harvesting, consolidating, preparing the close
  Scene 6 — Love & relationships arc across the year: Venus cycles, 7th house themes
  Scene 7 — Career & finances arc across the year: Jupiter/Saturn multi-month story
  Scene 8 — Closing affirmation: the year's master theme for {sign}, grounded in {element} strengths""",
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
Period start: {today}  →  Period end: {period_end}
Covers: {PERIOD_SPAN[period]}
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


def _build_moon_note(ctx: dict, period: str, sign: str) -> str:
    """
    Build a period-aware moon emphasis note.
    Daily: highlight a single phase if active.
    Weekly: mention phases that occur during the week.
    Monthly/yearly: list all major lunar events across the span.
    """
    moon_phase = ctx.get("moon_phase", "")
    moon_sign_val = ctx.get("moon_sign", "")

    if period == "daily":
        if moon_phase in ("New Moon", "Full Moon"):
            return (
                f"\n  ⚠️  {moon_phase} in {moon_sign_val} is active tomorrow — "
                f"this is a peak lunar energy moment the script MUST weave in."
            )
        return ""

    # For weekly/monthly/yearly, use the full lunar events list if the astro
    # engine provides it, otherwise fall back to the snapshot with a caveat.
    lunar_events = ctx.get("lunar_events_text", "")
    if lunar_events:
        label = {
            "weekly":  "this week",
            "monthly": "this month",
            "yearly":  "this year",
        }.get(period, "this period")
        return (
            f"\n  🌙 LUNAR EVENTS {label.upper()} (cover all of these across the scenes):\n"
            f"  {lunar_events}"
        )

    # Fallback: at least mention the opening phase
    if moon_phase in ("New Moon", "Full Moon"):
        return (
            f"\n  ⚠️  The period opens with a {moon_phase} in {moon_sign_val}. "
            f"Treat this as the emotional anchor for the opening of the period — "
            f"but do not imply it covers the whole {period}."
        )
    return ""


def generate_horoscope_script(
    sign: str,
    period: str,
    api_key_env: str = "GROQ_API_KEY_ASTRO",
    reference_date: date = None,
) -> dict:
    """
    Generate a horoscope video script grounded in real planetary positions.

    reference_date: the publish date (the date the content is FOR).
                    Planetary positions and transits are computed for this
                    date and the full span it covers.

    Returns a dict:
        title, hook, scenes [{narration, image_prompt}], closing_cta,
        description, tags
    """
    publish_date = reference_date or date.today()
    scenes_count = PERIOD_SCENES.get(period, 5)
    label        = PERIOD_LABEL.get(period, "tomorrow")
    horizon      = PERIOD_HORIZON.get(period, "the coming period")
    span         = PERIOD_SPAN.get(period, "this period")
    narration_wc = PERIOD_NARRATION_WORDS.get(period, "35-45")
    element      = SIGN_ELEMENTS[sign]
    ruler        = SIGN_RULERS[sign]["traditional"]
    symbol       = SIGN_SYMBOLS[sign]
    house        = SIGN_NATURAL_HOUSE[sign]
    house_theme  = HOUSE_THEMES[house]
    planet_theme = PLANET_THEMES.get(ruler, "")

    # Format the scene guide with sign-specific values
    scene_guide = PERIOD_SCENE_GUIDE[period].format(
        sign=sign,
        element=element,
    )

    # ── 1. Compute real sky positions ────────────────────────────────────────
    logger.info(f"Computing planetary positions for {sign} {period} (publish: {publish_date})")
    try:
        ctx      = get_planetary_context(period, publish_date)
        transits = get_sign_transits(sign, ctx)
        astro_brief = _build_astro_brief(sign, period, ctx, transits)
        logger.info(f"Planetary brief ready — {len(ctx['aspects'])} aspects found")
    except Exception as e:
        logger.warning(f"Astro engine error: {e} — falling back to minimal context")
        astro_brief = f"Period: {publish_date.isoformat()}\nSign: {sign} ({element}, ruled by {ruler})"
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

    # Ruler retrograde flag — period-aware phrasing
    ruler_rx_note = ""
    if transits.get("ruler_retrograde"):
        if period == "daily":
            timeframe = "today"
        elif period == "weekly":
            timeframe = "throughout this week"
        elif period == "monthly":
            timeframe = "for much of this month — check the exact station dates above"
        else:
            timeframe = "for part of this year — note the exact retrograde window above"
        ruler_rx_note = (
            f"\n  ⚠️  IMPORTANT: {ruler} (ruling planet of {sign}) is RETROGRADE {timeframe}. "
            f"This is a major theme — the script MUST address what this means for {sign}: "
            f"review, revision, delays, and internal focus in matters of {planet_theme}."
        )

    # Moon note — period-aware
    moon_note = _build_moon_note(ctx, period, sign)

    # Ingress emphasis — framed within the span
    ingress_note = ""
    if transits.get("arriving"):
        ingress_note = (
            f"\n  📌 Planets entering {sign} during this {period}: "
            + ", ".join(transits["arriving"])
            + f" — these arrivals are key story beats, distribute them across the "
            f"scenes that cover their part of the {period}."
        )

    # Date reference string for description — uses publish date, not run date
    date_ref = publish_date.strftime("%B %Y")

    user_prompt = f"""
You are writing a {period} horoscope video script for {sign} {symbol}.

This content is for {label} — it must cover {span} in full.
Do NOT write as if addressing today or this moment. Address the ENTIRE {period} ahead.

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
  — Inner growth: Moon phase(s), 12th house, Pluto/Neptune transits
• Reference actual degree positions or aspect names when relevant.
• {sign} is a {element} sign of {SIGN_MODALITIES[sign]} quality, naturally
  governing the {house}th house ({house_theme}).
• Tone: authoritative yet warm, specific yet uplifting.
  Never doom & gloom — even squares and retrogrades are growth opportunities.
• TEMPORAL SCOPE: each scene must be consistent with the part of the {period}
  it covers. Do not let early scenes describe the whole period — build across scenes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (JSON, exactly {scenes_count} scenes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "title": "YouTube Short title ≤60 chars — include {sign}, {period}, and a specific hook word",
  "hook": "One electric opening sentence referencing a specific transit (spoken in 3 seconds)",
  "scenes": [
    {{
      "narration": "Spoken narration for this scene, {narration_wc} words. Must reference specific planetary data and cover its designated part of the {period}.",
      "image_prompt": "Vivid image generation prompt — cosmic, ethereal, portrait orientation, NO text in image, colour palette matching {element} energy. Describe mood, lighting, celestial elements."
    }}
  ],
  "closing_cta": "Subscribe + like call-to-action, 1 sentence, mention horoscope frequency",
  "description": "YouTube/TikTok description 200-250 chars, include {date_ref}, emojis, sign, period",
  "tags": ["list of exactly 15 SEO tags as strings"]
}}

Scene allocation for {scenes_count} scenes — follow this EXACTLY:
{scene_guide}
"""

    logger.info(f"Calling Groq for {sign} {period} script (publish: {publish_date})…")
    raw = call_groq(
        prompt=user_prompt,
        system=system_prompt,
        temperature=0.75,
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
                "narration": f"The stars are aligned in your favour, {sign}. Trust the journey ahead.",
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
    reference_date: date = None,
) -> dict:
    """
    Optimise YouTube/TikTok metadata.
    Called separately so the Groq budget is split cleanly.

    reference_date: the publish date (must match what was passed to
                    generate_horoscope_script so date strings are consistent).
    """
    publish_date = reference_date or date.today()

    # All date strings derived from the publish date, not the run date
    date_str   = publish_date.strftime("%B %d, %Y")
    month_year = publish_date.strftime("%B %Y")
    year       = publish_date.year
    ruler      = SIGN_RULERS[sign]["traditional"]
    element    = SIGN_ELEMENTS[sign]
    symbol     = SIGN_SYMBOLS[sign]
    label      = PERIOD_LABEL[period]   # "tomorrow" / "next week" / etc.

    system = (
        "You are an expert YouTube SEO specialist who also understands astrology. "
        "Return ONLY valid JSON — no markdown fences, no extra text."
    )

    prompt = f"""
Optimise YouTube metadata for this {period} horoscope video.

Sign:         {sign} {symbol}
Period:       {period}
Publish date: {date_str}
Content for:  {label} (the {period} starting {date_str})

Draft title:       {script.get('title', '')}
Draft description: {script.get('description', '')}
Script hook:       {script.get('hook', '')}
Ruling planet:     {ruler}
Element:           {element}

Return JSON:
{{
  "title": "final title ≤60 chars — must include {sign}, {period}, and {month_year}",
  "description": "Full description 500-800 chars. Include: '{date_str}', sign {sign}, ruler {ruler}, element {element}, 3-4 relevant life areas covered, CTA to subscribe, hashtags on last line",
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
