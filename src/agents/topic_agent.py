import json
import os
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from groq import Groq

# ---------------------------------------------------------------------------
# Trending / current-events sourcing (Google News RSS — free, no API key).
# We stick to Science & Technology sections so headlines stay compatible with
# a "fascinating fact" Shorts format instead of drifting into hard news/politics.
# ---------------------------------------------------------------------------
_TRENDING_FEEDS = [
    "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/headlines/section/topic/HEALTH?hl=en-US&gl=US&ceid=US:en",
]
_TRENDING_TIMEOUT = 8
# Fraction of runs that should try to anchor on a real current headline
# before falling back to the evergreen topic pool.
_TRENDING_PROBABILITY = 0.6


# ---------------------------------------------------------------------------
# Diversified topic pool — 10 distinct categories, ~12 topics each
# ---------------------------------------------------------------------------
TOPIC_POOL = {
    "space": [
        "black holes", "neutron stars", "the speed of light", "dark matter",
        "the Big Bang", "time dilation", "quantum entanglement", "supernovae",
        "the multiverse", "exoplanets", "gravitational waves", "the cosmic web",
        "gamma-ray bursts", "hypervelocity stars", "magnetars", "rogue planets",
        "the Fermi paradox", "the Chandrasekhar limit", "the heat death of the universe",
        "the Oort Cloud", "dark energy", "the James Webb telescope", "cosmic strings",
    ],
    "human_body": [
        "how memory is stored in the brain", "the gut-brain connection",
        "why humans dream", "how pain actually works", "the immune system's memory",
        "how adrenaline transforms the body", "the lymphatic system",
        "why we feel goosebumps", "how vision is reconstructed by the brain",
        "how muscles grow after tearing", "the role of the appendix",
        "why yawning is contagious", "how the heart never gets tired",
        "why humans are the only animals that blush",
    ],
    "ocean": [
        "bioluminescent creatures", "the Mariana Trench", "underwater volcanoes",
        "how whale songs travel thousands of miles", "the giant squid",
        "ocean dead zones", "deep sea pressure survival", "underwater rivers",
        "the milky sea phenomenon", "how coral reefs die and regrow",
        "rogue waves", "ocean microplastics", "the Pacific trash vortex",
        "sea creatures that never sleep",
    ],
    "ancient_history": [
        "the lost city of Pompeii's last hours", "how the pyramids were actually built",
        "the Roman concrete that still stands today", "Viking navigation without compasses",
        "the Library of Alexandria's true fate", "ancient Greek computers",
        "the Black Death's impact on European DNA", "how ancient Romans brushed their teeth",
        "the mystery of the Indus Valley Civilization", "Spartan warrior training",
        "how Julius Caesar really died", "the longest siege in history",
    ],
    "animals": [
        "how octopuses think with their arms", "why crows never forget a face",
        "the mantis shrimp's 16-color vision", "how tardigrades survive anything",
        "the immortal jellyfish", "how elephants grieve their dead",
        "why some animals can regrow limbs", "the pistol shrimp's sonic weapon",
        "how dolphins sleep with one eye open", "why cats always land on their feet",
        "how ants farm fungi underground", "the migratory feats of Arctic terns",
        "how dogs read human emotions",
    ],
    "psychology": [
        "the Dunning-Kruger effect", "why humans fear uncertainty more than pain",
        "how sleep deprivation causes hallucinations", "the bystander effect",
        "why we make decisions emotionally and justify them logically",
        "how nostalgia affects the brain", "the psychology of procrastination",
        "why identical twins have different personalities", "the placebo effect's real power",
        "how social rejection activates physical pain pathways",
        "why humans are addicted to screens", "the science of déjà vu",
    ],
    "technology": [
        "how GPS actually knows your location", "why Wi-Fi slows through walls",
        "how lithium batteries degrade", "what quantum computers actually do",
        "how facial recognition works", "why the internet has physical undersea cables",
        "how encryption protects your messages", "why SSDs don't last forever",
        "the inside of a microchip", "how self-driving cars perceive the world",
        "what happens when a satellite dies", "how AI hallucinations happen",
    ],
    "earth_science": [
        "how earthquakes travel through the Earth", "why volcanoes can cool the planet",
        "the magnetic poles are shifting", "how plate tectonics reshape continents",
        "why the sky is blue", "the Yellowstone supervolcano",
        "how caves form underground", "why the Sahara used to be a jungle",
        "the fastest wind speeds ever recorded", "how lightning forms",
        "the deepest hole ever drilled", "why deserts get cold at night",
    ],
    "food_science": [
        "how fermentation creates alcohol", "why spicy food feels like pain",
        "how caffeine blocks tiredness", "why onions make you cry",
        "the chemistry of bread rising", "how sugar rewires the brain",
        "why some people can't taste bitterness", "how aging changes flavor",
        "why airplane food tastes bland", "the chemistry of caramelization",
        "how MSG became unfairly vilified",
    ],
    "mathematics": [
        "why infinity comes in different sizes", "the Monty Hall problem",
        "how prime numbers protect internet security", "Gödel's incompleteness theorem",
        "why 0.999… equals 1", "the Banach-Tarski paradox",
        "how fractals appear in nature", "the four-color map theorem",
        "why pi never repeats", "the birthday paradox",
        "how the Fibonacci sequence appears everywhere",
    ],
}

ALL_TOPICS = [t for topics in TOPIC_POOL.values() for t in topics]

# How many recent topics to show the LLM as exclusions
_HISTORY_WINDOW = 30
_HISTORY_FILE = Path("used_topics.json")


class TopicAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = "llama-3.3-70b-versatile"

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------
    def _load_history(self) -> list[str]:
        if _HISTORY_FILE.exists():
            try:
                return json.loads(_HISTORY_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_history(self, history: list[str], new_topic: str):
        history.append(new_topic)
        _HISTORY_FILE.write_text(json.dumps(history[-150:], indent=2))

    # ------------------------------------------------------------------
    # Pick a category not recently used
    # ------------------------------------------------------------------
    def _pick_category(self, recent: list[str]) -> str:
        """Rotate through categories to maximize variety."""
        # Count how many recent topics belong to each category
        category_counts = {cat: 0 for cat in TOPIC_POOL}
        for topic in recent:
            for cat, topics in TOPIC_POOL.items():
                if topic.lower() in [t.lower() for t in topics]:
                    category_counts[cat] += 1
                    break

        # Pick from the least-used categories
        min_count = min(category_counts.values())
        least_used = [cat for cat, count in category_counts.items() if count == min_count]
        return random.choice(least_used)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_topic(self) -> str:
        history = self._load_history()
        recent = history[-_HISTORY_WINDOW:]

        topic = (
            self._trending_topic(recent)
            or self._llm_topic(recent)
            or self._fallback_topic(recent)
        )
        self._save_history(history, topic)
        print(f"  📌 Topic selected: '{topic}'")
        return topic

    # ------------------------------------------------------------------
    # Trending: pull real current headlines and adapt one into a topic
    # ------------------------------------------------------------------
    def _fetch_trending_headlines(self, limit: int = 20) -> list[str]:
        headlines: list[str] = []
        feeds = list(_TRENDING_FEEDS)
        random.shuffle(feeds)
        for feed_url in feeds:
            try:
                resp = requests.get(
                    feed_url,
                    timeout=_TRENDING_TIMEOUT,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    if title_el is None or not title_el.text:
                        continue
                    # Google News titles look like "Headline - Publisher"; drop the source.
                    title = title_el.text.rsplit(" - ", 1)[0].strip()
                    if title and title not in headlines:
                        headlines.append(title)
            except Exception as e:
                print(f"  ⚠ Trending feed failed ({feed_url}): {e}")
            if len(headlines) >= limit:
                break
        return headlines[:limit]

    def _trending_topic(self, recent: list[str]) -> str | None:
        if random.random() > _TRENDING_PROBABILITY:
            return None  # keep some evergreen variety even when trending works

        headlines = self._fetch_trending_headlines()
        if not headlines:
            return None

        sample = random.sample(headlines, min(8, len(headlines)))
        exclusion_note = ""
        if recent:
            exclusion_note = (
                "\n\nDo NOT reuse any of these recently used topics:\n"
                + "\n".join(f"- {t}" for t in recent)
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You turn real current news headlines into a single specific, "
                            "fascinating YouTube Shorts fact-video topic. "
                            "Output ONLY the topic name — no explanation, no punctuation, no markdown. "
                            "If NONE of the headlines can be turned into a genuinely fascinating, "
                            "surprising, evergreen-feeling FACT (as opposed to routine news like "
                            "earnings, politics, or sports scores), output exactly: NONE."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Here are today's real headlines:\n"
                            + "\n".join(f"- {h}" for h in sample)
                            + "\n\nPick ONE and turn it into a specific, concrete topic for a "
                            "fascinating-facts Shorts video — something that lets the video explain "
                            "the surprising science, history, or mechanism behind what's currently "
                            "in the news. Keep it grounded in the real story, not generic."
                            + exclusion_note
                        ),
                    },
                ],
                temperature=0.9,
                max_tokens=30,
            )
            topic = response.choices[0].message.content.strip().strip("\"'.").lower()
            if not topic or topic == "none" or len(topic) > 90:
                return None
            if any(topic == r.lower() for r in recent):
                return None
            print(f"  📰 Trending topic derived from current headlines")
            return topic
        except Exception as e:
            print(f"  ⚠ Trending topic generation failed: {e} — falling back")
            return None

    # ------------------------------------------------------------------
    # LLM pick with exclusion list + category rotation
    # ------------------------------------------------------------------
    def _llm_topic(self, recent: list[str]) -> str | None:
        chosen_category = self._pick_category(recent)
        category_examples = ", ".join(
            f"'{t}'" for t in random.sample(TOPIC_POOL[chosen_category], min(3, len(TOPIC_POOL[chosen_category])))
        )

        exclusion_note = ""
        if recent:
            exclusion_note = (
                f"\n\nDo NOT suggest any of these recently used topics:\n"
                + "\n".join(f"- {t}" for t in recent)
            )

        # Human-readable category label for the prompt
        category_label = chosen_category.replace("_", " ")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You suggest one specific, fascinating topic for a YouTube Shorts video. "
                            "Output ONLY the topic name — no explanation, no punctuation, no markdown. "
                            "Be specific and varied. Avoid broad or generic topics."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Suggest one fascinating, SPECIFIC topic about '{category_label}' "
                            f"that would make a great YouTube Shorts fact video. "
                            f"Examples from this category: {category_examples}. "
                            f"Pick something concrete, surprising, and visually compelling. "
                            f"Be different from the examples above."
                            + exclusion_note
                        ),
                    },
                ],
                temperature=1.3,
                max_tokens=30,
            )
            topic = response.choices[0].message.content.strip().strip("\"'.").lower()
            if not topic or len(topic) > 80:
                return None

            if any(topic == r.lower() for r in recent):
                print(f"  ⚠ LLM repeated a recent topic ('{topic}') — using fallback.")
                return None

            return topic
        except Exception as e:
            print(f"  ⚠ TopicAgent LLM failed: {e} — using fallback pool")
            return None

    # ------------------------------------------------------------------
    # Fallback: random pick excluding recent history, with category rotation
    # ------------------------------------------------------------------
    def _fallback_topic(self, recent: list[str]) -> str:
        recent_lower = {r.lower() for r in recent}
        chosen_category = self._pick_category(recent)
        available = [
            t for t in TOPIC_POOL[chosen_category]
            if t.lower() not in recent_lower
        ]
        if not available:
            # Fall back to any topic not recently used
            available = [t for t in ALL_TOPICS if t.lower() not in recent_lower]
        if not available:
            available = ALL_TOPICS
        return random.choice(available)
