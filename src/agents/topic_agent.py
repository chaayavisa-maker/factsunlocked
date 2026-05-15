import os
import json
import re
import random
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import setup_logger

logger = setup_logger(__name__)

FALLBACK_TOPICS = [
    "The human body can produce enough electricity to power a small LED bulb",
    "Cleopatra lived closer in time to the Moon landing than to the building of the Great Pyramid",
    "There are more possible games of chess than atoms in the observable universe",
    "A day on Venus is longer than a year on Venus",
    "Octopuses have three hearts and blue blood",
    "The Eiffel Tower grows by 15cm in summer due to thermal expansion",
    "Honey found in ancient Egyptian tombs is still perfectly edible after 3000 years",
    "A group of flamingos is called a flamboyance",
]

class TopicAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def _get_trending_searches(self) -> list[str]:
        """Fetch Google Trends — falls back gracefully if blocked."""
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
            df = pt.trending_searches(pn="united_states")
            return df[0].tolist()[:20]
        except Exception as e:
            logger.warning(f"pytrends unavailable: {e}. Using built-in seed topics.")
            return [
                "science facts", "history secrets", "nature wonders",
                "space discoveries", "animal behavior", "human body",
                "ancient civilizations", "mind-blowing facts",
            ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_video_topic(self, niche: str = "amazing facts") -> dict:
        """
        Generates a viral-worthy video topic.
        Returns a dict with title, hook, topic, keywords, scenes_theme.
        """
        trending = self._get_trending_searches()
        trending_str = "\n".join(f"- {t}" for t in trending[:12])

        prompt = f"""You are a viral YouTube Shorts content strategist.
Niche: {niche}
Trending right now:
{trending_str}

Generate a SINGLE specific video topic for a 60-second YouTube Short.
Rules:
- Must be a genuinely surprising or counter-intuitive fact
- Should relate to something trending OR be timelessly fascinating
- Must work as a 60-second narrated video with 6 visual scenes
- Title must be < 60 characters and start with a number or power word

Respond ONLY with valid JSON, no markdown:
{{
  "title": "catchy video title < 60 chars",
  "topic": "one-line description of the core fact",
  "hook": "first 10 words that grab attention immediately",
  "scenes_theme": "brief visual style direction for the images",
  "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "wow_factor": "what makes this mind-blowing in one sentence"
}}"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=600,
        )

        text = response.choices[0].message.content.strip()
        # Strip any accidental markdown fences
        text = re.sub(r"```json|```", "", text).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Best-effort extraction
            match = re.search(r"\{.*\}", text, re.DOTALL)
            data = json.loads(match.group()) if match else {}

        # Ensure required fields
        data.setdefault("title", random.choice(FALLBACK_TOPICS)[:60])
        data.setdefault("topic", data["title"])
        data.setdefault("hook", data["title"])
        data.setdefault("scenes_theme", "cinematic, dramatic, educational")
        data.setdefault("keywords", ["facts", "didyouknow", "shorts"])
        data.setdefault("wow_factor", data["title"])

        logger.info(f"Topic chosen: {data['title']}")
        return data
