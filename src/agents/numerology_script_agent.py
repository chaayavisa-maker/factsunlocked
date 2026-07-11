"""
numerology_script_agent.py — AngelNumbers script generator.

Same anti-redundancy / narrative-variety design as horoscope_script_agent.py
(rotating narrative frames, per-scene rhetorical devices, forbidden openers),
adapted to numerology content. No live data source is needed — angel-number
meanings are static, so this agent is simpler and cheaper to run than the
astrology one (one Groq call for the script + one for SEO, same as AstroFacts).
"""

import json
import random
import re
from datetime import date

from src.utils.groq_client import call_groq
from src.utils.logger import get_logger
from config.angel_numbers import (
    NUMBER_SYMBOLS, NUMBER_CORE_MEANING, NUMBER_LIFE_DOMAIN,
    NUMBER_ROOT, ROOT_NUMBER_THEMES, COMMON_SIGHTINGS,
)

logger = get_logger(__name__)

PERIOD_SCENES = {"daily": 5}
PERIOD_NARRATION_WORDS = {"daily": "35-45"}

# ── Narrative style rotation (same purpose as AstroFacts' NARRATIVE_STYLES) ─

NARRATIVE_STYLES = [
    {
        "label": "the_sign_you_almost_missed",
        "frame": (
            "Frame this number as a message the viewer almost scrolled past — "
            "treat the act of them seeing this video as itself a sign. "
            "Tone: warm, slightly urgent, 'you were meant to see this'."
        ),
        "hook_instruction": "Open by describing the everyday moment of spotting this number and feeling a pull to look closer.",
    },
    {
        "label": "the_universe_is_confirming",
        "frame": (
            "Frame the number as direct confirmation from the universe/angels about a decision "
            "or feeling the viewer already has. Tone: reassuring, validating, 'you already knew'."
        ),
        "hook_instruction": "Open by naming a feeling viewers likely already have, then reveal the number confirms it.",
    },
    {
        "label": "the_countdown",
        "frame": (
            "Frame the number's appearance as the start of a countdown to a specific shift. "
            "Tone: anticipatory, cinematic, 'something is about to move'."
        ),
        "hook_instruction": "Open with a sense that a clock has started — something is about to change.",
    },
    {
        "label": "the_decoder",
        "frame": (
            "Frame the video as decoding a hidden message layer by layer — numerology root, "
            "spiritual meaning, and practical action each peel back one more layer. "
            "Tone: investigative, satisfying reveal."
        ),
        "hook_instruction": "Open by promising to decode exactly why this number keeps appearing.",
    },
    {
        "label": "the_gentle_warning",
        "frame": (
            "Frame the number as a gentle nudge to course-correct something specific, without "
            "being alarmist. Tone: caring older-sibling energy, direct but kind."
        ),
        "hook_instruction": "Open by naming the one area of life this number is asking the viewer to pay attention to.",
    },
    {
        "label": "the_permission_slip",
        "frame": (
            "Frame the number as cosmic permission to finally act on something the viewer has "
            "been hesitating on. Tone: liberating, encouraging, 'this is your green light'."
        ),
        "hook_instruction": "Open by naming something viewers have been putting off, then reveal this number is the green light.",
    },
]

SCENE_VOICES = [
    "STORY — narrate a brief relatable scenario of someone noticing this number",
    "DIRECT ADDRESS — speak as 'you', high specificity, naming a feeling or situation",
    "DECODE — break down the numerology root number and what it adds to the meaning",
    "AFFIRMATION ROOTED IN MEANING — an affirmation directly derived from this number's core meaning",
    "QUESTION — open with a rhetorical question the number raises, then answer it",
    "ACTION STEP — a concrete, specific thing to do in the next 24 hours because of this sign",
]

_FORBIDDEN_OPENERS = [
    "If you", "This number", "Seeing this", "The number", "Angels",
    "Today", "This is", "When you",
]

PERIOD_SCENE_GUIDE = {
    "daily": """\
  Scene 1 — Hook: why THIS number, right now, matters. Reference {sighting} as a relatable sighting moment.
  Scene 2 — Core spiritual meaning of {number} ONLY. Do not drift into other numbers.
  Scene 3 — Numerology root number {root} and what {root_theme} adds to the picture.
  Scene 4 — Practical life-area focus: {domain}. ONE concrete action tied to this domain.
  Scene 5 — Closing affirmation derived directly from {number}'s meaning, plus subscribe CTA setup.""",
}


def generate_numerology_script(
    number: str,
    period: str = "daily",
    api_key_env: str = "GROQ_API_KEY_ANGEL",
    reference_date: date = None,
) -> dict:
    """Generate an AngelNumbers video script. Mirrors generate_horoscope_script()."""
    publish_date = reference_date or date.today()
    scenes_count = PERIOD_SCENES.get(period, 5)
    narration_wc = PERIOD_NARRATION_WORDS.get(period, "35-45")
    symbol  = NUMBER_SYMBOLS.get(number, "✨")
    meaning = NUMBER_CORE_MEANING.get(number, "spiritual alignment")
    domain  = NUMBER_LIFE_DOMAIN.get(number, "personal growth")
    root    = NUMBER_ROOT.get(number, 0)
    root_theme = ROOT_NUMBER_THEMES.get(root, "personal growth")
    sighting = random.choice(COMMON_SIGHTINGS)

    style = random.choice(NARRATIVE_STYLES)
    voices = SCENE_VOICES.copy()
    random.shuffle(voices)
    scene_voices = [voices[i % len(voices)] for i in range(scenes_count)]
    scene_voice_block = "\n".join(f"  Scene {i+1} rhetorical device → {v}" for i, v in enumerate(scene_voices))
    forbidden_block = ", ".join(f'"{w}"' for w in _FORBIDDEN_OPENERS)

    scene_guide = PERIOD_SCENE_GUIDE[period].format(
        number=number, sighting=sighting, root=root, root_theme=root_theme, domain=domain,
    )

    system_prompt = (
        "You are a numerology and angel-numbers content writer with a compelling YouTube Shorts voice. "
        f"You write with NARRATIVE FRAME: {style['label'].upper().replace('_', ' ')} — {style['frame']} "
        "Return ONLY valid JSON — no markdown fences, no preamble, no extra text."
    )

    user_prompt = f"""
Write a {period} AngelNumbers video script about the number {number} {symbol}.

CORE MEANING TO BUILD FROM: {meaning}
LIFE DOMAIN FOCUS: {domain}
NUMEROLOGY ROOT NUMBER: {root} ({root_theme})

NARRATIVE STYLE THIS VIDEO: {style['label'].upper().replace('_', ' ')}
{style['frame']}
HOOK INSTRUCTION: {style['hook_instruction']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTI-REDUNDANCY RULES (STRICT):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• FORBIDDEN scene openers — NEVER start a narration with: {forbidden_block}
• No consecutive scenes may begin with the same word or phrase.
• Each scene must add NEW information — no restating the previous scene's point.
• The closing affirmation MUST be logically derived from {number}'s meaning above, not generic.
• NAME LIMIT: say the number "{number}" out loud in the SPOKEN narration at most TWICE across all
  {scenes_count} scenes (e.g. hook + closing only) — everywhere else refer to "this number" or address
  the viewer as "you". (Title/description/tags may still use "{number}" freely for SEO.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE VOICE ASSIGNMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{scene_voice_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (JSON, exactly {scenes_count} scenes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "title": "YouTube Short title <=60 chars, include {number} and 'meaning'",
  "hook": "One electric opening sentence ({style['hook_instruction']})",
  "scenes": [
    {{
      "narration": "Spoken narration, {narration_wc} words, matching its assigned rhetorical device.",
      "image_prompt": "Vivid image prompt — cosmic/ethereal, portrait orientation, no text in image, mood matching {number}'s energy."
    }}
  ],
  "closing_cta": "Subscribe + like CTA, 1 sentence, mention daily angel numbers",
  "description": "YouTube/TikTok description 200-250 chars, include {number}, emojis, 'angel number meaning'",
  "tags": ["list of exactly 15 SEO tag strings"]
}}

Scene allocation — follow this EXACTLY:
{scene_guide}
"""

    logger.info(f"Calling Groq [{style['label']}] for angel number {number}…")
    raw = call_groq(
        prompt=user_prompt,
        system=system_prompt,
        temperature=0.9,
        max_tokens=1600,
        api_key_env=api_key_env,
    )

    try:
        script = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            script = json.loads(match.group())
        else:
            raise ValueError(f"Groq returned non-JSON for {number}:\n{raw[:300]}")

    scenes = script.get("scenes", [])
    if len(scenes) < scenes_count:
        logger.warning(f"Groq returned {len(scenes)} scenes, expected {scenes_count} — padding")
        while len(scenes) < scenes_count:
            scenes.append({
                "narration": f"Trust the timing of {number} appearing in your life right now.",
                "image_prompt": f"ethereal glowing number {number}, cosmic background, mystical light, portrait",
            })
        script["scenes"] = scenes
    elif len(scenes) > scenes_count:
        script["scenes"] = scenes[:scenes_count]

    script["_style"] = style["label"]
    logger.info(f"Script ready: '{script.get('title', '?')}' [style={style['label']}]")
    return script


def generate_seo_metadata(
    number: str,
    period: str,
    script: dict,
    api_key_env: str = "GROQ_API_KEY_ANGEL",
    reference_date: date = None,
) -> dict:
    """Optimise YouTube/TikTok metadata. Mirrors generate_seo_metadata() in horoscope_script_agent.py."""
    publish_date = reference_date or date.today()
    date_str = publish_date.strftime("%B %d, %Y")
    meaning = NUMBER_CORE_MEANING.get(number, "")

    system = (
        "You are an expert YouTube SEO specialist who understands numerology and angel numbers. "
        "Return ONLY valid JSON — no markdown fences, no extra text."
    )

    prompt = f"""
Optimise YouTube metadata for this angel-number video.

Number:       {number}
Core meaning: {meaning}
Publish date: {date_str}

Draft title:       {script.get('title', '')}
Draft description: {script.get('description', '')}
Script hook:       {script.get('hook', '')}

Return JSON:
{{
  "title": "final title <=60 chars — must include '{number}' and 'meaning'",
  "description": "Full description 400-600 chars. Include '{number} angel number meaning', a CTA to subscribe, hashtags on last line",
  "tags": ["exactly 20 SEO tag strings — mix of: '{number} angel number', 'angel numbers meaning', 'numerology', '{number} meaning', spiritual/manifestation terms"]
}}
"""
    raw = call_groq(prompt, system=system, temperature=0.4, max_tokens=700, api_key_env=api_key_env)
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {
        "title": script.get("title", f"{number} Angel Number Meaning"),
        "description": script.get("description", ""),
        "tags": script.get("tags", []),
    }
