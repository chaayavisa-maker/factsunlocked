import os
import random
from groq import Groq


TOPIC_POOL = [
    "black holes", "neutron stars", "the speed of light", "dark matter",
    "the Big Bang", "time dilation", "quantum entanglement", "supernovae",
    "the multiverse", "exoplanets", "the Milky Way", "solar flares",
    "the event horizon", "wormholes", "the cosmic microwave background",
    "antimatter", "the Oort Cloud", "magnetars", "gamma-ray bursts",
    "the life cycle of stars", "the Fermi paradox", "space-time",
    "the Voyager probes", "Pluto", "Saturn's rings", "Jupiter's storms",
]


class TopicAgent:
    def __init__(self):
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = "llama-3.1-70b-versatile"

    def get_topic(self) -> str:
        """Pick a trending-ish space topic using LLM + a fallback pool."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You suggest one specific space science topic for a YouTube Shorts video. "
                            "Output only the topic name — no explanation, no punctuation, no markdown. "
                            "Examples: 'neutron stars', 'the James Webb telescope', 'dark energy'"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Suggest one fascinating space or astronomy topic that would make a great "
                            "YouTube Shorts video today. Pick something specific and surprising."
                        ),
                    },
                ],
                temperature=1.0,
                max_tokens=30,
            )
            topic = response.choices[0].message.content.strip().strip("\"'").lower()
            if topic:
                return topic
        except Exception as e:
            print(f"TopicAgent LLM failed: {e} — using fallback pool")

        return random.choice(TOPIC_POOL)
