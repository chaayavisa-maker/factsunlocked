import os
import json
import re
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ScriptAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def write_script(self, topic: dict, num_scenes: int = 6) -> dict:
        """
        Writes a complete video script with per-scene narration,
        image prompts, and on-screen text.
        Returns a dict with 'scenes' list and 'outro'.
        """
        prompt = f"""You are a top YouTube Shorts scriptwriter. Write a COMPLETE script for a 60-second video.

Topic: {topic['title']}
Core fact: {topic['topic']}
Hook: {topic['hook']}
Visual style: {topic.get('scenes_theme', 'cinematic, dramatic')}

Write exactly {num_scenes} scenes. Each scene is ~10 seconds when narrated at normal pace.

Rules:
- Scene 1 MUST open with the hook — grab attention instantly
- Build curiosity, reveal the fact gradually, end with a mind-blowing conclusion
- Narration per scene: 2-3 SHORT sentences, 25-35 words max
- Image prompt: detailed, visual, cinematic — describes WHAT TO SHOW on screen
- On-screen text: 1 bold statement, < 8 words, complements the narration
- No filler words. Every sentence must earn its place.

Respond ONLY with valid JSON, no markdown fences:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "narration text read aloud — 25-35 words",
      "image_prompt": "detailed Stable Diffusion prompt for the background image",
      "on_screen_text": "BOLD SHORT TEXT < 8 WORDS",
      "duration_hint": 10
    }}
  ],
  "outro": "Subscribe for more mind-blowing facts every day!"
}}"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=2000,
        )

        text = response.choices[0].message.content.strip()
        text = re.sub(r"```json|```", "", text).strip()

        try:
            script = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            script = json.loads(match.group()) if match else self._fallback_script(topic, num_scenes)

        # Validate and repair
        if "scenes" not in script or len(script["scenes"]) < num_scenes:
            logger.warning("Script incomplete — using fallback filler for missing scenes")
            script = self._pad_scenes(script, topic, num_scenes)

        script["topic"] = topic
        logger.info(f"Script ready: {len(script['scenes'])} scenes")
        return script

    def _fallback_script(self, topic: dict, num_scenes: int) -> dict:
        """Emergency fallback if Groq returns unparseable output."""
        hook = topic.get("hook", topic["title"])
        fact = topic.get("topic", topic["title"])
        scenes = []
        templates = [
            (f"{hook}. What you're about to learn will change how you see the world.", f"photo of {fact}, dramatic lighting, cinematic", "WAIT FOR THIS"),
            (f"Here's the mind-blowing part: {fact}.", f"extreme closeup of {fact}, 4k", "MIND BLOWN"),
            ("Scientists were stunned when they discovered this. Most people have no idea.", "scientists in laboratory, discovery moment, dramatic", "NOBODY KNOWS THIS"),
            ("The implications are even more surprising. Let's break it down.", "infographic style, educational, clean", "HERE'S WHY"),
            ("This changes everything we thought we knew about the world.", f"wide shot of {fact}, epic scale, golden hour", "EVERYTHING CHANGES"),
            ("Follow for more facts that will absolutely blow your mind every single day.", "galaxy stars space, wonder, awe inspiring, cinematic", "FOLLOW FOR MORE"),
        ]
        for i, (narr, img, txt) in enumerate(templates[:num_scenes], 1):
            scenes.append({
                "scene_number": i,
                "narration": narr,
                "image_prompt": img,
                "on_screen_text": txt,
                "duration_hint": 10,
            })
        return {"scenes": scenes, "outro": "Subscribe for more!"}

    def _pad_scenes(self, script: dict, topic: dict, target: int) -> dict:
        """Pads a short script to the required number of scenes."""
        fallback = self._fallback_script(topic, target)
        existing = script.get("scenes", [])
        while len(existing) < target:
            existing.append(fallback["scenes"][len(existing)])
        script["scenes"] = existing[:target]
        return script
