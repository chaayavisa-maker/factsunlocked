import json
import os
from groq import Groq


class ScriptAgent:
    def __init__(self, settings: dict):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = "llama-3.1-70b-versatile"
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
  "title": "...",
  "image_queries": ["visual description 1", ...]
}}

RULES:

hook — max 8 words. A question or shocking claim that stops scrolling.
  GOOD: "Your skeleton completely replaces itself every decade."
  GOOD: "This planet rains molten glass sideways."
  BAD: "Did you know that..."
  BAD: "Today we will learn about..."

scenes — exactly {self.body_count} facts. Each fact max 15 words. Short. Punchy. Astonishing.
  Every fact must feel like a revelation, not a textbook line.

payoff — 1 sentence, max 12 words. Rewards the viewer for watching to the end.
  Example: "And scientists still cannot explain why."

title — max 60 characters. Must include a number or a shocking claim.
  Example: "5 Space Facts That Will Break Your Brain"

image_queries — exactly {self.scenes_count} vivid visual descriptions, one per scene (hook → facts → payoff).
  These are used to generate images. Be specific and visual.
  Example: "dramatic close-up of a neutron star surface glowing orange"
  Do NOT include text or watermarks in descriptions.

Topic: {topic}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You output only valid JSON. No markdown, no preamble, no code fences, no explanation."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=1000
        )

        text = response.choices[0].message.content.strip()
        # Strip any accidental markdown fences
        text = text.replace("```json", "").replace("```", "").strip()

        script = json.loads(text)

        # Validate structure — fill defaults if LLM misbehaves
        if "hook" not in script:
            script["hook"] = f"You won't believe this {self.niche} fact."
        if "scenes" not in script or not isinstance(script["scenes"], list):
            script["scenes"] = [f"Fact about {topic}."] * self.body_count
        if "payoff" not in script:
            script["payoff"] = "Science is stranger than fiction."
        if "title" not in script:
            script["title"] = f"Mind-Blowing {topic} Facts"
        if "image_queries" not in script or len(script["image_queries"]) < self.scenes_count:
            script["image_queries"] = [topic] * self.scenes_count

        # Ensure exactly the right counts
        script["scenes"] = script["scenes"][:self.body_count]
        script["image_queries"] = script["image_queries"][:self.scenes_count]

        return script

    def get_full_narration_text(self, script: dict) -> str:
        """Build the complete narration string from script."""
        parts = [script["hook"]] + script["scenes"] + [script["payoff"]]
        return ". ".join(parts)
