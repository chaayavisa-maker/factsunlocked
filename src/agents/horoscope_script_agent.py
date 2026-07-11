"""
HoroscopeScriptAgent — v2 (anti-redundancy rewrite)
─────────────────────────────────────────────────────
Root causes of redundancy fixed in this version:

  1. NARRATIVE STYLES (was missing entirely)
     12 rotating styles injected per-call so every video has a distinct
     dramatic frame — not just "here are your transits".

  2. SCENE VOICE VARIETY (new)
     Each scene is assigned a different rhetorical device (story, metaphor,
     warning, affirmation, question, prediction) so consecutive scenes
     can't all sound like narration bullets.

  3. STRICT ANTI-REPEAT RULES (new in prompt)
     Explicit constraints: no scene may begin the same way as the previous
     one; forbidden opener words list; each life-area is covered once only.

  4. TEMPERATURE BOOST (0.75 → 0.92)
     Higher temperature at the generation stage for more surprising
     word choices. SEO call stays at 0.4 for reliability.

  5. SIGN-SPECIFIC PERSONALITY SEEDS (new)
     Each sign gets a personality archetype injected into the system prompt
     so Aries sounds nothing like Pisces even on the same day.

  6. PERIOD-AWARE TENSE + SCOPE ENFORCEMENT (tightened)
     Scene guide now uses imperative MUST/NEVER language and explicitly
     names which life area each scene owns — no scene can bleed into
     another's territory.

Pipeline per call (unchanged from v1):
  1. astro_engine.get_planetary_context()  → live sky positions
  2. astro_engine.get_sign_transits()      → sign-specific interpretation
  3. build prompt with style + voice injection → sent to Groq
  4. parse and return structured JSON
"""

import json
import random
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

PERIOD_SCENES = {
    "daily":   5,
    "weekly":  6,
    "monthly": 7,
    "yearly":  8,
}

PERIOD_LABEL = {
    "daily":   "tomorrow",
    "weekly":  "next week",
    "monthly": "next month",
    "yearly":  "next year",
}

PERIOD_NARRATION_WORDS = {
    "daily":   "35-45",
    "weekly":  "45-55",
    "monthly": "55-65",
    "yearly":  "65-80",
}

PERIOD_HORIZON = {
    "daily":   "the next 24 hours",
    "weekly":  "the next 7 days",
    "monthly": "the coming month",
    "yearly":  "the full year ahead",
}

PERIOD_SPAN = {
    "daily":   "a single day",
    "weekly":  "a full 7-day week",
    "monthly": "a full calendar month",
    "yearly":  "a full 12-month year",
}

# ── NEW: Narrative style rotation ─────────────────────────────────────────────
# One of these is chosen at random per video. Each gives the LLM a completely
# different dramatic frame to hang the planetary facts on, so two Aries dailies
# generated on the same day still sound like different videos.

NARRATIVE_STYLES = [
    {
        "label": "the_turning_point",
        "frame": (
            "Frame this reading as a pivotal turning point the viewer is standing at RIGHT NOW. "
            "Every transit is evidence that their life is about to shift. "
            "Tone: urgent, cinematic, 'everything changes from here'."
        ),
        "hook_instruction": "Open with a 'before/after' framing — something is ending so something new can begin.",
    },
    {
        "label": "the_hidden_gift",
        "frame": (
            "Frame every transit — even tense squares and retrogrades — as a hidden gift in disguise. "
            "The universe is conspiring in their favour even when it feels like friction. "
            "Tone: warmly conspiratorial, empowering, 'you don't see it yet, but…'."
        ),
        "hook_instruction": "Open with a revelation: something that seemed like a problem is actually the breakthrough.",
    },
    {
        "label": "the_cosmic_weather",
        "frame": (
            "Frame the planets as weather — the viewer is a traveller who needs to know what to pack. "
            "Trines are sunny days, squares are storms to navigate with the right gear, "
            "retrogrades are fog that clears. Tone: practical, grounded, meteorologist meets mystic."
        ),
        "hook_instruction": "Open with a weather metaphor that instantly captures the dominant transit's energy.",
    },
    {
        "label": "the_character_arc",
        "frame": (
            "Frame this period as one chapter in the viewer's ongoing life story. "
            "Mention what was happening astrologically last month/year as the 'setup', "
            "and this period as the plot development. "
            "Tone: novelistic, narrative, 'in the last episode of your life…'."
        ),
        "hook_instruction": "Open by referencing where the viewer has JUST been, then pivot to what's coming.",
    },
    {
        "label": "the_challenge_accepted",
        "frame": (
            "Frame every tension in the chart as a challenge the universe has issued specifically to this sign. "
            "The viewer is the hero and the transits are the trials they were made to pass. "
            "Tone: bold, martial, 'you were built for exactly this moment'."
        ),
        "hook_instruction": "Open with a direct challenge or call-to-action — the planets are daring them.",
    },
    {
        "label": "the_slow_reveal",
        "frame": (
            "Build the reading like a mystery being solved across scenes. "
            "Each scene reveals one more piece of the cosmic puzzle until the final scene pays it all off. "
            "Tone: suspenseful, layered, each scene ends with a hint of 'but there's more…'."
        ),
        "hook_instruction": "Open with an intriguing question or half-revealed fact that demands the viewer keep watching.",
    },
    {
        "label": "the_permission_slip",
        "frame": (
            "Frame the reading as cosmic permission to finally do the thing the viewer has been hesitating on. "
            "The planets are aligning to say 'now is your moment — stop waiting'. "
            "Tone: liberating, direct, like a best friend who refuses to let you play small."
        ),
        "hook_instruction": "Open by naming something the viewer has been putting off — the stars just said GO.",
    },
    {
        "label": "the_inside_track",
        "frame": (
            "Frame the reading as insider information — the viewer is getting access to cosmic data "
            "most people are completely unaware of. "
            "Tone: confidential, 'you and I know something others don't', slightly elite."
        ),
        "hook_instruction": "Open as if sharing a secret — something specific about this period that most people will miss.",
    },
    {
        "label": "the_energy_forecast",
        "frame": (
            "Frame the reading like an energy report: where will the viewer feel drained, where will they feel unstoppable. "
            "Ground every transit in a physical/emotional energy level. "
            "Tone: holistic, body-aware, 'your energy is a resource — here's how to spend it'."
        ),
        "hook_instruction": "Open by describing the overall energy level of this period — high voltage, low tide, electric, etc.",
    },
    {
        "label": "the_three_domains",
        "frame": (
            "Structure the reading explicitly around three life domains the planets are activating: "
            "one domain per cluster of scenes. Make it clear which domain each scene belongs to. "
            "Tone: organised, actionable, 'here's what to focus on and in what order'."
        ),
        "hook_instruction": "Open by naming all three domains being activated — give the viewer the map upfront.",
    },
    {
        "label": "the_ancestral_pattern",
        "frame": (
            "Frame the transits as the universe helping the viewer break an old pattern or repeat a legacy. "
            "The outer planet transits especially connect to deeper cycles. "
            "Tone: profound, soulful, healing — 'your chart knows what your mind hasn't caught up to yet'."
        ),
        "hook_instruction": "Open by naming the pattern or cycle that's completing or beginning.",
    },
    {
        "label": "the_market_report",
        "frame": (
            "Frame the reading like a financial analyst's report — where to invest energy, where to hold back, "
            "what's overvalued right now, what's undervalued and about to surge. "
            "Tone: strategic, confident, slightly corporate but cosmic — 'your ROI on effort this week is highest in…'."
        ),
        "hook_instruction": "Open with a 'buy / hold / sell' metaphor applied to energy, decisions, or relationships.",
    },
]

# ── NEW: Scene voice/rhetoric rotation ───────────────────────────────────────
# Each scene in a video is assigned a different rhetorical device.
# This prevents 5 consecutive narration bullets all starting "This period…"

SCENE_VOICES = [
    "STORY — tell a brief illustrative scenario (2-3 sentences as if something is already unfolding for the viewer)",
    "METAPHOR — use one extended metaphor from nature, sport, cooking, or architecture to explain the transit",
    "DIRECT ADDRESS — speak directly as 'you' with high specificity: 'You've been feeling X. Here's why, and here's what shifts'",
    "PREDICTION — make a specific, date-anchored or event-anchored prediction grounded in the transit data",
    "WARNING + REFRAME — name a specific risk from the chart, then immediately flip it into an opportunity",
    "AFFIRMATION ROOTED IN DATA — write an affirmation that is directly derived from a specific transit, not generic",
    "QUESTION — open the scene with a rhetorical question the transit raises, then answer it with planetary evidence",
    "CONTRAST — describe what this same energy looked like last cycle vs what's different NOW",
]

# ── NEW: Sign personality archetypes ─────────────────────────────────────────
# Injected into the system prompt so each sign's videos have a consistent
# editorial voice distinct from other signs.

SIGN_PERSONALITIES = {
    "Aries":       "bold, impatient, warrior-poet — speaks in short punchy sentences, always forward-moving",
    "Taurus":      "sensory, unhurried, luxurious — uses tactile language, grounds abstractions in physical experience",
    "Gemini":      "quick-witted, dual-natured, curious — pivots fast, uses contrast and duality, conversational",
    "Cancer":      "intuitive, emotionally rich, protective — speaks to the inner life, uses home/water metaphors",
    "Leo":         "theatrical, regal, generous — grand statements, dramatic reveals, makes the viewer feel chosen",
    "Virgo":       "precise, analytical, quietly radical — notices what others miss, uses specific detail, builds to insight",
    "Libra":       "balanced, aesthetic, relationship-focused — uses 'on one hand / on the other', elegant phrasing",
    "Scorpio":     "intense, psychological, unflinching — names the thing no one will say, deep undercurrent always present",
    "Sagittarius": "philosophical, expansive, adventurous — big-picture perspective, uses travel/exploration metaphors",
    "Capricorn":   "strategic, pragmatic, ambitious — speaks to results and legacy, no fluff, long-game thinking",
    "Aquarius":    "visionary, unconventional, collective — frames personal transits in social/collective context",
    "Pisces":      "poetic, mystical, compassionate — uses water/dream/music imagery, speaks to the soul not the mind",
}

# ── Per-period scene allocation ───────────────────────────────────────────────

PERIOD_SCENE_GUIDE = {
    "daily": """\
  Scene 1 — Opening energy: the SINGLE most important transit or aspect for tomorrow ONLY.
             MUST name the specific planet and aspect. DO NOT summarise the whole day — just the dominant energy.
  Scene 2 — Love & relationships: ONE Venus/7th house insight for tomorrow. THIS SCENE ONLY covers love.
  Scene 3 — Career & finances: ONE Saturn/Jupiter/10th house insight for tomorrow. THIS SCENE ONLY covers work/money.
  Scene 4 — Personal growth & wellbeing: Moon phase + inner planet aspects + self-care angle.
  Scene 5 — Closing affirmation: MUST derive directly from {sign}'s {element} strengths AND the dominant transit.
             DO NOT repeat anything already said. This must feel like a payoff, not a summary.""",

    "weekly": """\
  Scene 1 — Opening: hook + the dominant transit shaping the WHOLE week (name planet, aspect, dates).
  Scene 2 — Monday to Wednesday energy: specific early-week transit or ingress. DO NOT cover the whole week.
  Scene 3 — Love & relationships this week: ONE Venus/7th house arc. THIS SCENE ONLY covers relationships.
  Scene 4 — Career & finances this week: ONE Saturn/Jupiter/10th house arc. THIS SCENE ONLY covers work/money.
  Scene 5 — Late-week peak: the single most important day or transit of Thursday–Saturday. Name the date.
  Scene 6 — Weekend + affirmation: Sunday energy and a closing affirmation derived from {sign}'s {element} strengths.
             DO NOT repeat any life area already covered. Must feel earned, not tagged on.""",

    "monthly": """\
  Scene 1 — Opening: the defining planetary story arc for the WHOLE month. Big picture only.
  Scene 2 — Weeks 1–2: specific ingresses, aspects, or stations in the FIRST half. DO NOT drift into second half.
  Scene 3 — Weeks 3–4: how energy SHIFTS in the second half. What builds, what resolves. SECOND half only.
  Scene 4 — Love & relationships this month: Venus/7th house arc across all four weeks. THIS SCENE ONLY covers love.
  Scene 5 — Career & finances this month: Saturn/Jupiter/10th house. THIS SCENE ONLY covers work/money.
  Scene 6 — Standout peak moment: the SINGLE most important day or transit of the entire month. Name the date.
  Scene 7 — Closing affirmation: month's overarching theme grounded in {sign}'s {element} strengths.
             Must synthesise the month's arc without repeating specific facts from earlier scenes.""",

    "yearly": """\
  Scene 1 — Opening: the SINGLE biggest planetary shift defining {sign}'s entire year. Big picture only.
  Scene 2 — Q1 (Jan–Mar): which themes OPEN the year. Seeds to plant. DO NOT drift into Q2.
  Scene 3 — Q2 (Apr–Jun): how energy accelerates or pivots mid-year. Q2 only.
  Scene 4 — Q3 (Jul–Sep): the year's peak zone — name the specific transit(s). Q3 only.
  Scene 5 — Q4 (Oct–Dec): harvesting, consolidating, preparing the close. Q4 only.
  Scene 6 — Love & relationships arc: Venus cycles and 7th house themes across the WHOLE year.
             THIS SCENE ONLY covers relationships. DO NOT repeat quarterly content.
  Scene 7 — Career & finances arc: Jupiter/Saturn multi-month story. THIS SCENE ONLY covers work/money.
  Scene 8 — Closing affirmation: the year's master theme for {sign} grounded in {element} strengths.
             Must feel like a conclusion to a year-long story, not a generic pep talk.""",
}

# ── FORBIDDEN OPENERS (injected into every prompt) ───────────────────────────
# These are the most common redundancy patterns the LLM falls into.

_FORBIDDEN_OPENERS = [
    "This week", "This month", "This period", "This year", "This reading",
    "As a", "The stars", "The planets", "The cosmos", "The universe",
    "For you", "Get ready", "Brace yourself", "Today", "Tomorrow",
    "In this", "During this", "With this",
]


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

def _build_astro_brief(sign: str, period: str, ctx: dict, transits: dict) -> str:
    today       = ctx["reference_date"]
    period_end  = ctx["period_end"]
    ruler_trad  = transits["ruler_trad"]
    ruler_mod   = transits["ruler_mod"]
    element     = SIGN_ELEMENTS[sign]
    modality    = SIGN_MODALITIES[sign]
    house       = transits["house"]
    house_theme = transits["house_theme"]
    symbol      = SIGN_SYMBOLS[sign]

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
    moon_phase    = ctx.get("moon_phase", "")
    moon_sign_val = ctx.get("moon_sign", "")

    if period == "daily":
        if moon_phase in ("New Moon", "Full Moon"):
            return (
                f"\n  ⚠️  {moon_phase} in {moon_sign_val} is active tomorrow — "
                f"this is a peak lunar energy moment the script MUST weave in."
            )
        return ""

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

    if moon_phase in ("New Moon", "Full Moon"):
        return (
            f"\n  ⚠️  The period opens with a {moon_phase} in {moon_sign_val}. "
            f"Treat this as the emotional anchor for the opening of the period — "
            f"but do not imply it covers the whole {period}."
        )
    return ""


def _assign_scene_voices(n_scenes: int) -> list[str]:
    """
    Assign a distinct rhetorical device to each scene.
    Never assigns the same voice to consecutive scenes.
    """
    voices = SCENE_VOICES.copy()
    random.shuffle(voices)
    assigned = []
    for i in range(n_scenes):
        # Rotate through shuffled voices; skip if same as previous
        voice = voices[i % len(voices)]
        if assigned and voice == assigned[-1]:
            voice = voices[(i + 1) % len(voices)]
        assigned.append(voice)
    return assigned


def generate_horoscope_script(
    sign: str,
    period: str,
    api_key_env: str = "GROQ_API_KEY_ASTRO",
    reference_date: date = None,
) -> dict:
    """
    Generate a horoscope video script grounded in real planetary positions.
    v2: adds narrative style rotation, scene voice variety, and anti-redundancy rules.
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

    # Pick a random narrative style and assign scene voices
    style         = random.choice(NARRATIVE_STYLES)
    scene_voices  = _assign_scene_voices(scenes_count)
    personality   = SIGN_PERSONALITIES[sign]

    scene_guide = PERIOD_SCENE_GUIDE[period].format(sign=sign, element=element)

    # ── 1. Planetary data ─────────────────────────────────────────────────────
    logger.info(f"Computing planetary positions for {sign} {period} (publish: {publish_date.isoformat()})")
    try:
        ctx         = get_planetary_context(period, publish_date)
        transits    = get_sign_transits(sign, ctx)
        astro_brief = _build_astro_brief(sign, period, ctx, transits)
        logger.info(f"Planetary brief ready — {len(ctx['aspects'])} aspects found")
    except Exception as e:
        logger.warning(f"Astro engine error: {e} — falling back to minimal context")
        astro_brief = f"Period: {publish_date.isoformat()}\nSign: {sign} ({element}, ruled by {ruler})"
        transits, ctx = {}, {}

    # ── 2. Supplementary notes ────────────────────────────────────────────────
    ruler_rx_note = ""
    if transits.get("ruler_retrograde"):
        timeframe = {
            "daily":   "today",
            "weekly":  "throughout this week",
            "monthly": "for much of this month — check the exact station dates above",
            "yearly":  "for part of this year — note the exact retrograde window above",
        }.get(period, "this period")
        ruler_rx_note = (
            f"\n  ⚠️  IMPORTANT: {ruler} (ruling planet of {sign}) is RETROGRADE {timeframe}. "
            f"This is a major theme — the script MUST address what this means for {sign}: "
            f"review, revision, delays, and internal focus in matters of {planet_theme}."
        )

    moon_note = _build_moon_note(ctx, period, sign)

    ingress_note = ""
    if transits.get("arriving"):
        ingress_note = (
            f"\n  📌 Planets entering {sign} during this {period}: "
            + ", ".join(transits["arriving"])
            + f" — distribute these arrivals across the scenes that cover their part of the {period}."
        )

    date_ref = {
        "daily":   publish_date.strftime("%B %-d, %Y"),
        "weekly":  f"Week of {publish_date.strftime('%B %-d, %Y')}",
        "monthly": publish_date.strftime("%B %Y"),
        "yearly":  str(publish_date.year),
    }.get(period, publish_date.strftime("%B %Y"))

    # ── 3. Build scene voice assignments block ────────────────────────────────
    scene_voice_block = "\n".join(
        f"  Scene {i+1} rhetorical device → {v}"
        for i, v in enumerate(scene_voices)
    )

    # ── 4. Build forbidden openers block ─────────────────────────────────────
    forbidden_block = ", ".join(f'"{w}"' for w in _FORBIDDEN_OPENERS)

    # ── 5. Build system + user prompts ───────────────────────────────────────
    system_prompt = (
        f"You are a professional Western astrologer with a compelling YouTube presence. "
        f"Your editorial voice for {sign} specifically is: {personality}. "
        f"You write with NARRATIVE FRAME: {style['label'].upper().replace('_', ' ')} — {style['frame']} "
        f"You ground every prediction in REAL planetary transits. "
        f"Your videos never sound like the previous one — each has a distinct dramatic shape. "
        f"You almost never say the sign's name out loud in narration ({sign} appears at most once, "
        f"in the hook or closing line only) — you address the viewer as 'you' instead. "
        f"Return ONLY valid JSON — no markdown fences, no preamble, no extra text."
    )

    user_prompt = f"""
You are writing a {period} horoscope video script for {sign} {symbol}.
This content is for {label} — it must cover {span} in full.
DO NOT write as if addressing today or this moment — address the ENTIRE {period} ahead.

NARRATIVE STYLE THIS VIDEO: {style["label"].upper().replace("_", " ")}
{style["frame"]}
HOOK INSTRUCTION: {style["hook_instruction"]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REAL PLANETARY DATA (use ALL of this — never invent positions):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{astro_brief}
{ruler_rx_note}{moon_note}{ingress_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTI-REDUNDANCY RULES (STRICT — violations make the video unwatchable):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• FORBIDDEN scene openers — NEVER start a narration with: {forbidden_block}
• NO consecutive scenes may begin with the same word or phrase.
• Each life area (love, career, health, growth) appears in EXACTLY ONE scene. No repeats.
• Each scene MUST reference a different planet, transit, or aspect from the data above.
  Two scenes may NOT both be "about Venus" or "about Saturn" unless the period is long enough
  to split their arc meaningfully between scenes.
• The hook MUST be specific to this {sign} + this {period}'s dominant transit — not a generic opener.
• The closing affirmation MUST be logically derived from the planetary data, not a generic pep talk.
• NAME LIMIT: say "{sign}" out loud in the SPOKEN narration at most ONCE across all {scenes_count} scenes
  (ideally in the hook or the closing line only). In every other scene, address the viewer as "you" —
  never repeat the sign's name as a crutch. (The title, description, and tags may still use "{sign}"
  as many times as needed for SEO — this limit applies ONLY to spoken narration.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE VOICE ASSIGNMENTS (each scene uses a DIFFERENT rhetorical device):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{scene_voice_block}

Use these devices exactly as assigned. A STORY scene narrates a scenario. 
A METAPHOR scene builds one extended image. A PREDICTION names a specific outcome.
This is what prevents five consecutive narration bullets from sounding identical.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (JSON, exactly {scenes_count} scenes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "title": "YouTube Short title ≤60 chars — include {sign}, {period}, and a specific hook word",
  "hook": "One electric opening sentence referencing a specific transit ({style['hook_instruction']})",
  "scenes": [
    {{
      "narration": "Spoken narration for this scene, {narration_wc} words. Must use the assigned rhetorical device AND reference specific planetary data AND cover only its designated life area.",
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

    logger.info(f"Calling Groq [{style['label']}] for {sign} {period} (publish: {publish_date})…")
    raw = call_groq(
        prompt=user_prompt,
        system=system_prompt,
        temperature=0.92,   # higher than v1 (was 0.75) for more surprising word choices
        max_tokens=2000,
        api_key_env=api_key_env,
    )

    # ── 6. Parse JSON ─────────────────────────────────────────────────────────
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

    # Validate scene count
    scenes = script.get("scenes", [])
    if len(scenes) < scenes_count:
        logger.warning(f"Groq returned {len(scenes)} scenes, expected {scenes_count} — padding")
        while len(scenes) < scenes_count:
            scenes.append({
                "narration": f"The stars are aligned in your favour, {sign}. Trust the journey ahead.",
                "image_prompt": f"cosmic nebula in {SIGN_ELEMENTS[sign]} colours, ethereal and mystical, portrait",
            })
        script["scenes"] = scenes
    elif len(scenes) > scenes_count:
        script["scenes"] = scenes[:scenes_count]

    # Store style for debugging + A/B analysis
    script["_style"] = style["label"]
    script["_scene_voices"] = scene_voices

    logger.info(f"Script ready: '{script.get('title', '?')}' [style={style['label']}]")
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
    SEO call uses lower temperature (0.4) for reliability — creativity is for the script.
    """
    publish_date = reference_date or date.today()
    date_str   = publish_date.strftime("%B %d, %Y")
    month_year = publish_date.strftime("%B %Y")
    year       = publish_date.year
    ruler      = SIGN_RULERS[sign]["traditional"]
    element    = SIGN_ELEMENTS[sign]
    symbol     = SIGN_SYMBOLS[sign]
    label      = PERIOD_LABEL[period]

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
    raw = call_groq(prompt, system=system, temperature=0.4, max_tokens=900, api_key_env=api_key_env)
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {
        "title":       script.get("title", f"{sign} {period.title()} Horoscope {month_year}"),
        "description": script.get("description", ""),
        "tags":        script.get("tags", []),
    }
