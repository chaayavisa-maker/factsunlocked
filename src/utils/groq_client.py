"""
Thin wrapper around the Groq REST API.
Each channel can use a different GROQ token (to avoid rate-limit sharing).
"""

import os
import json
import httpx
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def call_groq(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = "llama-3.1-70b-versatile",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    api_key_env: str = "GROQ_API_KEY",
) -> str:
    """
    Call Groq chat completion.

    Parameters
    ----------
    api_key_env : str
        Name of the environment variable that holds the API key.
        FactsUnlocked uses ``GROQ_API_KEY``.
        AstroFacts    uses ``GROQ_API_KEY_ASTRO``.
    """
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise EnvironmentError(
            f"Environment variable '{api_key_env}' is not set. "
            "Add it as a GitHub Actions secret."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }

    logger.info(f"Calling Groq ({model}) via {api_key_env} ...")
    with httpx.Client(timeout=60) as client:
        resp = client.post(GROQ_API_URL, headers=headers, json=payload)
        resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
