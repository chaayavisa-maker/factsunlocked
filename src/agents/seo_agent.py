import os
import json
import re
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import setup_logger

logger = setup_logger(__name__)

MAX_TITLE_LEN = 100       # YouTube limit
MAX_DESC_LEN = 5000
MAX_TAGS = 500            # YouTube tag character budget


class SEOAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate(self, topic: dict, script: dict, extra_description: str = "") -> dict:
        """Alias used by main.py — delegates to generate_metadata."""
        return self.generate_metadata(topic, script, extra_description=extra_description)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def generate_metadata(self, topic: dict, script: dict, extra_description: str = "") -> dict:
        """
        Generates YouTube-optimised title, description, and tags.
        Inserts #Shorts + affiliate CTA into the description.
        """
        narrations = " ".join(
            s["narration"] for s in script.get("scenes", [])
        )

        prompt = f"""You are a YouTube SEO expert specialised in viral Shorts.

Video topic: {topic['title']}
Core fact: {topic.get('topic', topic['title'])}
Script summary: {narrations[:600]}

Generate YouTube metadata. Rules:
- Title: < 100 chars, emotionally compelling, includes a hook number or power word
- Description: 150-250 words. Start with the hook. Include the full fact. Add 3 related questions people might search. End with CTA to subscribe.
- Tags: 20-30 tags, mix of broad and specific. Include "Shorts" and "#Shorts".
- Hashtags line: top 5 hashtags to append at end of description.

Respond ONLY with valid JSON, no markdown:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...],
  "hashtags": ["#Shorts", "#facts", ...]
}}"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1200,
        )

        text = response.choices[0].message.content.strip()
        text = re.sub(r"```json|```", "", text).strip()

        try:
            meta = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            meta = json.loads(match.group()) if match else {}

        # --- Sanitise and enforce limits ---
        title = meta.get("title", topic["title"])[:MAX_TITLE_LEN]

        tags = meta.get("tags", [])
        # Ensure core tags always present
        must_have = ["Shorts", "shorts", "facts", "didyouknow", "amazingfacts", "viral"]
        for t in must_have:
            if t not in tags:
                tags.insert(0, t)

        # Trim tag budget
        tag_budget, final_tags = 0, []
        for t in tags:
            if tag_budget + len(t) + 1 <= MAX_TAGS:
                final_tags.append(t)
                tag_budget += len(t) + 1

        hashtags = meta.get("hashtags", ["#Shorts", "#Facts", "#DidYouKnow"])
        hashtag_line = " ".join(hashtags[:8])

        description = meta.get("description", topic.get("topic", ""))
        if extra_description:
            description = f"{description}\n\n{extra_description}"
        description = f"{description}\n\n{hashtag_line}"
        description = description[:MAX_DESC_LEN]

        result = {
            "title": title,
            "description": description,
            "tags": final_tags,
            "category_id": "27",          # Education
            "default_language": "en",
        }

        logger.info(f"SEO ready | title='{title}' | tags={len(final_tags)}")
        return result
