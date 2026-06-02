import os
import json
import re
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_TITLE_LEN = 100
MAX_DESC_LEN = 5000
MAX_TAGS = 500


class SEOAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate(self, topic, script: dict, extra_description: str = "") -> dict:
        """Public entry point called by main.py."""
        return self.generate_metadata(topic, script, extra_description=extra_description)

    @staticmethod
    def _enforce_number_in_title(title: str) -> str:
        """
        Ensure title starts with a number (3-9 range).
        If no number is found, prepend one based on the content.
        
        Examples:
          "Amazing NASA Facts" → "5 Amazing NASA Facts"
          "7 Secrets About Space" → "7 Secrets About Space" (already has number)
        """
        # Check if title already contains a number
        if re.search(r'\b[1-9]\b', title):
            return title
        
        # If no number, prepend a random number (3-9)
        import random
        number = random.randint(3, 9)
        
        # Find a good insertion point (after first word or at start)
        words = title.split()
        if len(words) > 1:
            # Insert after first word if it's too short, otherwise at start
            first_word = words[0]
            if len(first_word) < 4:  # e.g., "The", "You", "Why"
                return f"{first_word} {number} {' '.join(words[1:])}"
        
        return f"{number} {title}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def generate_metadata(self, topic, script: dict, extra_description: str = "") -> dict:
        # Normalise topic
        if isinstance(topic, dict):
            topic_title = topic.get("title", str(topic))
            topic_fact = topic.get("topic", topic_title)
        else:
            topic_title = str(topic)
            topic_fact = str(topic)

        # Build full narration summary from all script parts
        parts = (
            [script.get("hook", "")]
            + [
                (s.get("narration", "") if isinstance(s, dict) else str(s))
                for s in script.get("scenes", [])
            ]
            + [script.get("payoff", "")]
        )
        full_narration = " ".join(p for p in parts if p)

        prompt = f"""You are a YouTube SEO expert specialised in viral Shorts.

Video topic: {topic_title}
Core fact: {topic_fact}
Full script: {full_narration[:800]}

Generate YouTube metadata. Strict rules:
- Title: under 100 chars. MUST include a specific number (3-9 range) at the start. Examples: "5 Mind-Blowing Facts", "7 Secrets", "3 Reasons Why". Emotionally charged. No clickbait that doesn't deliver.
- Description: 200–300 words. Open with the hook verbatim. Expand the key facts with one extra detail each. Add 4 related search questions people might type. Close with a subscribe CTA. Write in second person ("you").
- Tags: 25–35 tags. Mix single words, 2-word phrases, and 3-word phrases. Always include "Shorts", "shorts", "space facts", "did you know", "mind blowing facts", "science facts".
- Hashtags: top 6 hashtags ranked by likely reach. Always include #Shorts and #SpaceFacts.

Respond ONLY with valid JSON, no markdown fences:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...],
  "hashtags": ["#Shorts", "#SpaceFacts", ...]
}}"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You output only valid JSON. No markdown, no preamble, no explanation."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.65,
            max_tokens=1400,
        )

        text = response.choices[0].message.content.strip()
        text = re.sub(r"```json|```", "", text).strip()

        try:
            meta = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            meta = json.loads(match.group()) if match else {}

        # Sanitise and enforce limits
        title = meta.get("title", topic_title)[:MAX_TITLE_LEN]
        
        # Enforce number in title (backup if Groq doesn't comply)
        title = self._enforce_number_in_title(title)
        title = title[:MAX_TITLE_LEN]

        tags = meta.get("tags", [])
        must_have = ["Shorts", "shorts", "space facts", "facts", "did you know",
                     "science", "amazingfacts", "viral", "educational"]
        for t in must_have:
            if t not in tags:
                tags.insert(0, t)

        tag_budget, final_tags = 0, []
        for t in tags:
            if tag_budget + len(t) + 1 <= MAX_TAGS:
                final_tags.append(t)
                tag_budget += len(t) + 1

        hashtags = meta.get("hashtags", ["#Shorts", "#SpaceFacts", "#DidYouKnow"])
        hashtag_line = " ".join(hashtags[:8])

        description = meta.get("description", topic_fact)
        if extra_description:
            description = f"{description}\n\n{extra_description}"
        description = f"{description}\n\n{hashtag_line}"
        description = description[:MAX_DESC_LEN]

        result = {
            "title": title,
            "description": description,
            "tags": final_tags,
            "category_id": "27",        # Education
            "default_language": "en",
        }

        logger.info(f"SEO ready | title='{title}' | tags={len(final_tags)}")
        return result
