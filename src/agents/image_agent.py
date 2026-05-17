import os
import time
import requests
from pathlib import Path
from urllib.parse import quote


class ImageAgent:
    def __init__(self, settings: dict):
        self.visual_style = settings["channel"]["visual_style"]
        self.width = 1080
        self.height = 1920
        self.timeout = 90
        self.max_retries = 3

    def _build_url(self, query: str) -> str:
        # Append consistent style to every prompt
        full_prompt = f"{query}, {self.visual_style}"
        encoded = quote(full_prompt)
        return (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={self.width}&height={self.height}&nologo=true&enhance=true"
        )

    def _download(self, url: str, save_path: str) -> bool:
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, timeout=self.timeout, stream=True)
                if resp.status_code == 200 and len(resp.content) > 10_000:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    return True
            except Exception as e:
                print(f"Image download attempt {attempt + 1} failed: {e}")
                time.sleep(5)
        return False

    def generate_all(self, script: dict, workspace: Path) -> list:
        """Generate one image per scene. Returns list of local file paths."""
        queries = script.get("image_queries", [])
        image_paths = []

        for i, query in enumerate(queries):
            save_path = str(workspace / f"image_{i:02d}.jpg")
            url = self._build_url(query)

            print(f"Generating image {i+1}/{len(queries)}: {query[:60]}...")
            success = self._download(url, save_path)

            if not success:
                # Fallback: use a simpler prompt
                fallback_url = self._build_url(query.split(",")[0])
                success = self._download(fallback_url, save_path)

            if success:
                image_paths.append(save_path)
            else:
                print(f"WARNING: Image {i} failed entirely, skipping.")

        return image_paths
