"""
groq_client.py — thin wrapper around the Groq Python SDK.
Uses the same free-tier approach as the original repo.
Each channel passes its own api_key_env to avoid sharing rate limits.
"""

import os
from groq import Groq
from src.utils.logger import get_logger

logger = get_logger(__name__)


def call_groq(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    api_key_env: str = "GROQ_API_KEY",
) -> str:
    """
    Call Groq chat completion via the official SDK.

    Parameters
    ----------
    api_key_env : str
        Name of the environment variable holding the API key.
        FactsUnlocked uses ``GROQ_API_KEY``.
        AstroFacts    uses ``GROQ_API_KEY_ASTRO``.
    """
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise EnvironmentError(
            f"Environment variable '{api_key_env}' is not set. "
            "Add it as a GitHub Actions secret."
        )

    client = Groq(api_key=api_key)
    logger.info(f"Calling Groq ({model}) via {api_key_env}...")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response.choices[0].message.content.strip()
