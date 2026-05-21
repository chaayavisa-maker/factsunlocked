import json
import os
import random
from pathlib import Path
from groq import Groq


TOPIC_POOL = [
    "black holes", "neutron stars", "the speed of light", "dark matter",
    "the Big Bang", "time dilation", "quantum entanglement", "supernovae",
    "the multiverse", "exoplanets", "the Milky Way", "solar flares",
    "the event horizon", "wormholes", "the cosmic microwave background",
    "antimatter", "the Oort Cloud", "magnetars", "gamma-ray bursts",
    "the life cycle of stars", "the Fermi paradox", "space-time",
    "the Voyager probes", "Pluto", "Saturn's rings", "Jupiter's storms",
    "dark energy", "the James Webb telescope", "cosmic strings",
    "the death of the sun", "rogue planets", "the largest black hole",
    "the coldest place in the universe", "the oldest star", "stellar nurseries",
    "the asteroid belt", "the Great Filter", "tidal locking", "the Hubble constant",
    "gravitational waves", "the Chandrasekhar limit", "Lagrange points",
    "the cosmic web", "binary star systems", "the heat death of the universe",
    "terraforming Mars", "the rings of Uranus", "io's volcanoes",
    "the galactic center", "hypervelocity stars", "the Dyson sphere hypothesis",
]

# How many recent topics to show the LLM as exclusions
_HISTORY_WINDOW = 20
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
        # Keep only the last 100 entries so the file doesn't grow forever
        _HISTORY_FILE.write_text(json.dumps(history[-100:], indent=2))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_topic(self) -> str:
        history = self._load_history()
        recent = history[-_HISTORY_WINDOW:]  # last N for the prompt

        topic = self._llm_topic(recent) or self._fallback_topic(recent)
        self._save_history(history, topic)
        print(f"  📌 Topic selected: '{topic}'")
        return topic

    # ------------------------------------------------------------------
    # LLM pick with exclusion list
    # ------------------------------------------------------------------
    def _llm_topic(self, recent: list[str]) -> str | None:
        exclusion_note = ""
        if recent:
            exclusion_note = (
                f"\n\nDo NOT suggest any of these recently used topics:\n"
                + "\n".join(f"- {t}" for t in recent)
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You suggest one specific space science topic for a YouTube Shorts video. "
                            "Output ONLY the topic name — no explanation, no punctuation, no markdown. "
                            "Be specific and varied. Good examples: "
                            "'the Chandrasekhar limit', 'rogue planets', "
                            "'the cosmic web', 'hypervelocity stars', "
                            "'io's volcanic activity', 'the Hubble tension'"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Suggest one fascinating, SPECIFIC space or astronomy topic "
                            "that would make a great YouTube Shorts video. "
                            "Avoid broad topics like 'space exploration' or 'the universe'. "
                            "Pick something concrete, surprising, and visually compelling."
                            + exclusion_note
                        ),
                    },
                ],
                temperature=1.2,   # higher = more variety
                max_tokens=30,
            )
            topic = response.choices[0].message.content.strip().strip("\"'.").lower()
            if not topic or len(topic) > 80:
                return None

            # Reject if LLM ignored the exclusion list
            if any(topic == r.lower() for r in recent):
                print(f"  ⚠ LLM repeated a recent topic ('{topic}') — using fallback.")
                return None

            return topic
        except Exception as e:
            print(f"  ⚠ TopicAgent LLM failed: {e} — using fallback pool")
            return None

    # ------------------------------------------------------------------
    # Fallback: random pick excluding recent history
    # ------------------------------------------------------------------
    def _fallback_topic(self, recent: list[str]) -> str:
        recent_lower = {r.lower() for r in recent}
        available = [t for t in TOPIC_POOL if t.lower() not in recent_lower]
        if not available:
            available = TOPIC_POOL  # all used — reset
        return random.choice(available)
