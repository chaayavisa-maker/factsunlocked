import json
import os
import random
from groq import Groq


# Tone/style variants to prevent every script sounding identical
SCRIPT_STYLES = [
    {
        "label": "shocking_scale",
        "hook_guidance": "Start with a number or measurement so extreme it defies belief.",
        "structure": "Open with the shocking number → explain WHY it's so extreme → escalate with what it means for humans → end with the mind-bending implication.",
        "hook_example": "A teaspoon of a neutron star weighs a billion tons — and that's the lightest part.",
        "tone": "matter-of-fact delivery of insane facts — let the numbers do the shocking",
    },
    {
        "label": "story_reveal",
        "hook_guidance": "Open mid-story, as if something is already happening.",
        "structure": "Drop into a scene → reveal the surprising truth behind it → escalate with related facts → end with a twist or unexpected connection.",
        "hook_example": "In 1986, a diver descended into a cave — and discovered something that rewrote human history.",
        "tone": "narrative, suspenseful — feel like a thriller unfolding",
    },
    {
        "label": "you_didnt_know",
        "hook_guidance": "Make it personal — connect the fact directly to the viewer's daily life or body.",
        "structure": "Connect to viewer → reveal the hidden mechanism → escalate with counterintuitive implications → end with the 'never see it the same way' payoff.",
        "hook_example": "Every single cell in your body is making a decision right now — and most of them aren't asking your brain.",
        "tone": "conversational and personal — feel like a friend revealing a secret",
    },
    {
        "label": "versus_comparison",
        "hook_guidance": "Use an extreme comparison to familiar objects or everyday experiences.",
        "structure": "Establish the weird comparison → unpack why it works → pile on more comparisons → end with the biggest, most absurd comparison.",
        "hook_example": "The pressure at the bottom of the ocean would crush a submarine like an empty soda can — in milliseconds.",
        "tone": "vivid, tactile comparisons — make the abstract feel physical",
    },
    {
        "label": "forbidden_knowledge",
        "hook_guidance": "Frame it as something 'they' don't want you to know or something almost nobody realizes.",
        "structure": "The surprising claim → the evidence that proves it → why most people get this wrong → the real truth payoff.",
        "hook_example": "Scientists have known this for 40 years — and most textbooks still get it completely wrong.",
        "tone": "conspiratorial but factual — correcting a common misconception dramatically",
    },
]


class ScriptAgent:
    def __init__(self, settings: dict):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = "llama-3.3-70b-versatile"
        self.niche = settings["channel"]["niche"]
        self.visual_style = settings["channel"]["visual_style"]
        self.scenes_count = settings["video"]["scenes_count"]
        self.body_count = self.scenes_count - 2

    def generate(self, topic: str) -> dict:
        style = random.choice(SCRIPT_STYLES)

        prompt = f"""You write viral YouTube Shorts scripts about fascinating facts.

Output ONLY valid JSON. No markdown. No explanation. No preamble.

Format:
{{
  "hook": "...",
  "scenes": ["fact 1", "fact 2", ...],
  "payoff": "...",
  "outro": "...",
  "title": "...",
  "image_queries": ["visual description 1", ...]
}}

TODAY'S STYLE: {style["label"].upper().replace("_", " ")}
Tone: {style["tone"]}
Structure: {style["structure"]}

RULES:

hook — 1 punchy sentence, 8–14 words. {style["hook_guidance"]}
  Use present tense. Make it feel urgent and personal.
  GOOD example of this style: "{style["hook_example"]}"
  NEVER start with "Did you know" or "Today we will learn"
  NEVER be vague or educational-sounding

scenes — exactly {self.body_count} facts. Each fact 20–30 words. Use vivid, sensory language.
  Build on each other — escalate the wow factor.
  Include specific numbers, comparisons to everyday things, or mind-bending scale.
  GOOD: "If you fell into a black hole, time would slow so much that the entire future of the universe would flash by before you crossed the event horizon."
  BAD: "This is a very interesting phenomenon."
  Each fact must feel DIFFERENT in structure from the others — vary sentence rhythm, vary opening words.

payoff — 1 sentence, 15–20 words. The gut-punch finale.
  Reveal the most astonishing implication or unexpected connection.
  It must feel like a twist — reward viewers for watching to the end.

outro — 1 short sentence, call to action. Max 12 words. Warm but urgent.
  NEVER use "if this blew/blows/blown your mind" or any "mind-blowing" / "mind blown" phrasing — it's overused and banned.
  Try instead: "Save this — you'll want to share it." or "Follow for a new one every day." or "Which fact surprised you most? Tell me below."

title — max 60 characters. Include a power word (Shocking / Secret / Insane / Hidden / Real Truth).
  Must feel clickable and specific to THIS topic.

image_queries — exactly {self.scenes_count} vivid visual descriptions, one per scene (hook → facts → payoff).
  Be hyper-specific — color, lighting, perspective, mood, artistic style.
  GOOD: "extreme close-up of an octopus eye, golden iridescent, underwater blue light, photorealistic macro photography"
  BAD: "octopus"
  Do NOT include text, words, watermarks, or UI in descriptions.
  Vary between: cinematic photography, scientific illustration, dramatic aerial view, microscopy, satellite imagery.

Topic: {topic}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a world-class YouTube Shorts scriptwriter. "
                        "You output ONLY valid JSON — no markdown, no preamble, no code fences. "
                        "Every script must have a DISTINCT personality based on the style given. "
                        "Vary sentence structure, vary openings, vary rhythm. Never repeat yourself."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            max_tokens=1500,
        )

        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()

        script = json.loads(text)
        script["_style"] = style["label"]  # store for debugging

        # Validate and fill defaults
        if "hook" not in script:
            script["hook"] = f"What scientists just discovered about {topic} will change how you see the world."
        if "scenes" not in script or not isinstance(script["scenes"], list):
            script["scenes"] = [f"Astonishing fact about {topic}."] * self.body_count
        if "payoff" not in script:
            script["payoff"] = "And this discovery is changing everything scientists thought they knew."
        if "outro" not in script:
            script["outro"] = "Follow for a new fact every day."
        if "title" not in script:
            script["title"] = f"The Shocking Truth About {topic.title()}"
        if "image_queries" not in script or len(script["image_queries"]) < self.scenes_count:
            script["image_queries"] = [
                f"dramatic cinematic scene related to {topic}, photorealistic, 4K, intense lighting"
            ] * self.scenes_count

        # Enforce exact counts
        script["scenes"] = script["scenes"][:self.body_count]
        script["image_queries"] = script["image_queries"][:self.scenes_count]

        return script

    def get_full_narration_text(self, script: dict) -> str:
        """Build the complete narration string from script."""
        parts = (
            [script["hook"]]
            + script["scenes"]
            + [script["payoff"]]
            + [script.get("outro", "")]
        )
        return " ".join(p for p in parts if p)
