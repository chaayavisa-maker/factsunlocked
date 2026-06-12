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
        """
        if re.search(r'\b[1-9]\b', title):
            return title

        import random
        number = random.randint(3, 9)
        words = title.split()
        if len(words) > 1:
            first_word = words[0]
            if len(first_word) < 4:
                return f"{first_word} {number} {' '.join(words[1:])}"

        return f"{number} {title}"

    @staticmethod
    def _sanitize_tags(tags: list) -> list:
        """
        Clean tags before the budget loop:
          - Split any comma-merged tags the LLM returns as one string
          - Strip characters YouTube rejects: < > " and leading/trailing whitespace
          - Drop empty strings
        """
        sanitised = []
        for t in tags:
            t = str(t).strip()
            # LLM sometimes returns "tag1, tag2" as a single tag
            parts = [p.strip() for p in t.split(",")]
            for p in parts:
                p = p.replace("<", "").replace(">", "").replace('"', "").strip()
                if p:
                    sanitised.append(p)
        return sanitised

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
- Description: 500-800 words. Open with the hook verbatim. Expand the key facts with one extra detail each. Add 4 related search questions people might actually type into YouTube. Include a subscribe CTA. Close with 5-6 relevant hashtags on the last line. Write in second person ("you"). This longer description is essential for YouTube search ranking.
- Tags: 25-35 tags. ALL tags must be 100% specific to the topic "{topic_title}". Do NOT include generic tags like "space facts", "did you know", "science facts", or "Shorts" unless the video is actually about space. Tags must match what someone searching for THIS specific topic would type. Mix single words, 2-word phrases, and 3-word phrases. Always include "Shorts" and "shorts" as platform tags.
- Hashtags: top 6 hashtags ranked by likely reach. Always include #Shorts. The remaining 5 must be topic-specific.

Respond ONLY with valid JSON, no markdown fences:
{{
  "title": "...",
  "description": "...",
  "tags": ["tag1", "tag2", ...],
  "hashtags": ["#Shorts", "#{topic_title.replace(' ', '')}Facts", ...]
}}"""

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You output only valid JSON. No markdown, no preamble, no explanation. Tags must be 100% specific to the given topic — never use generic placeholders."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.65,
            max_tokens=1800,
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
        title = self._enforce_number_in_title(title)
        title = title[:MAX_TITLE_LEN]

        # Per-tag sanitization: strip invalid chars, split comma-merged tags, drop empties
        tags = self._sanitize_tags(meta.get("tags", []))

        # Inject platform tags if missing
        must_have = ["Shorts", "shorts"]
        for t in must_have:
            if t not in tags:
                tags.insert(0, t)

        # Enforce 500-char total budget
        tag_budget, final_tags = 0, []
        for t in tags:
            if tag_budget + len(t) + 1 <= MAX_TAGS:
                final_tags.append(t)
                tag_budget += len(t) + 1

        hashtags = meta.get("hashtags", ["#Shorts", "#DidYouKnow", "#Facts"])
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

        logger.info(f"SEO ready | title='{title}' | tags={len(final_tags)} | desc_len={len(description)}")
        return result
