import os
import random
import requests
from pathlib import Path


# Kevin MacLeod — CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
# Credit: "Music by Kevin MacLeod (incompetech.com)"
# These are direct MP3 download links — no signup, no API key required.
MUSIC_TRACKS = [
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Cipher.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Floating%20Cities.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Investigations.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Lightless%20Dawn.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Impact%20Moderato.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Hyperfun.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/District%20Four.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Darkest%20Child.mp3",
]

# Attribution — CC-BY requires this in every video description
MUSIC_CREDIT = "Music: Kevin MacLeod (incompetech.com) — Licensed under CC BY 4.0"


class MusicAgent:
    def __init__(self, settings: dict):
        self.volume = settings["video"].get("music_volume", 0.12)

    def get_track(self, workspace: Path) -> str | None:
        """Download a random background track. Returns local path or None."""
        save_path = str(workspace / "background_music.mp3")

        urls = MUSIC_TRACKS.copy()
        random.shuffle(urls)

        for url in urls:
            try:
                print(f"Downloading music: {url.split('/')[-1]}")
                resp = requests.get(url, timeout=30, stream=True)
                if resp.status_code == 200 and len(resp.content) > 50_000:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    print("Music downloaded successfully.")
                    return save_path
            except Exception as e:
                print(f"Music URL failed ({url}): {e}")
                continue

        print("WARNING: All music URLs failed — video will have no background music.")
        return None

    @staticmethod
    def get_credit() -> str:
        return MUSIC_CREDIT
