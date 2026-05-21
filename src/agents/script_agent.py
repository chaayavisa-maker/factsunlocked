import json
import os
from groq import Groq


class ScriptAgent:
    def __init__(self, settings: dict):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = "llama-3.3-70b-versatile"
        self.niche = settings["channel"]["niche"]
        self.visual_style = settings["channel"]["visual_style"]
        self.scenes_count = settings["video"]["scenes_count"]
        # hook + payoff take 2 slots; the rest are body facts
        self.body_count = self.scenes_count - 2

    def generate(self, topic: str) -> dict:
        prompt = f"""You write viral YouTube Shorts scripts about {self.niche}.

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

RULES:

hook — 1 punchy sentence, 8–14 words. A question or shocking claim that stops scrolling.
  Use present tense. Make it feel urgent and personal.
  GOOD: "This planet rains molten glass sideways at 5,000 mph."
  GOOD: "A teaspoon of a neutron star weighs a billion tons."
  BAD: "Did you know that..." — never start with this
  BAD: "Today we will learn about..." — never educational filler

scenes — exactly {self.body_count} facts. Each fact is 20–30 words. Use vivid, sensory language.
  Build on each other — each fact should escalate the wow factor.
  Include specific numbers, comparisons to everyday things, or mind-bending scale.
  GOOD: "If you fell into a black hole, time would slow so much that the entire future of the universe would flash by before you crossed the event horizon."
  BAD: "Black holes are very dense objects in space."

payoff — 1 sentence, 15–20 words. The gut-punch finale that rewards viewers for watching.
  Reveal the most astonishing implication or the twist nobody expects.
  Example: "And right now, one of these events is happening just 8,000 light-years from Earth."

outro — 1 short sentence, call to action. Max 12 words. Warm but urgent.
  Example: "Follow for a new space fact that'll break your brain every day."

title — max 60 characters. Must include a number or a shocking power word.
  Example: "5 Space Facts That Will Break Your Brain"

image_queries — exactly {self.scenes_count} vivid visual descriptions, one per scene (hook → facts → payoff).
  Be hyper-specific — color, lighting, perspective, mood.
  GOOD: "extreme close-up of a neutron star crust, glowing orange and blue, cracking under immense gravity, dramatic space backdrop"
  BAD: "neutron star"
  Do NOT include text, words, watermarks, or UI in descriptions.

Topic: {topic}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a world-class YouTube Shorts scriptwriter. "
                        "You output ONLY valid JSON — no markdown, no preamble, no code fences, no explanation. "
                        "Every scene must be specific, visceral, and escalate the sense of wonder."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=1400,
        )

        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()

        script = json.loads(text)

        # Validate and fill defaults if LLM misbehaves
        if "hook" not in script:
            script["hook"] = f"You won't believe what scientists discovered about {topic}."
        if "scenes" not in script or not isinstance(script["scenes"], list):
            script["scenes"] = [f"Astonishing fact about {topic}."] * self.body_count
        if "payoff" not in script:
            script["payoff"] = "And scientists are still struggling to explain why this is possible."
        if "outro" not in script:
            script["outro"] = "Follow for a new space fact that'll break your brain every day."
        if "title" not in script:
            script["title"] = f"Mind-Blowing {topic.title()} Facts"
        if "image_queries" not in script or len(script["image_queries"]) < self.scenes_count:
            script["image_queries"] = [
                f"dramatic cinematic space scene related to {topic}, photorealistic, 4K"
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
