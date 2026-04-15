"""
Unified LLM provider factory supporting Groq and OpenAI.

Usage:
    from src.llm.provider import build_instructor_client, get_llm_config

    cfg = get_llm_config()
    client = build_instructor_client(cfg["provider"])
"""
import os
from pathlib import Path

import instructor
import yaml


def get_llm_config() -> dict:
    """
    Load LLM configuration from config/settings.yaml.

    Returns:
        dict with keys "provider" and "model".
    """
    settings_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
    with open(settings_path) as f:
        settings = yaml.safe_load(f)
    llm = settings.get("llm", {})
    return {
        "provider": llm.get("provider", "groq"),
        "model": llm.get("model", "llama-3.1-8b-instant"),
    }


def build_instructor_client(provider: str) -> instructor.Instructor:
    """
    Build an instructor-wrapped LLM client for the given provider.

    Args:
        provider: "groq" or "openai"

    Returns:
        instructor.Instructor instance ready for structured completions.

    Raises:
        ValueError: If provider is unknown or the required API key is not set.
    """
    if provider == "groq":
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Add it to your .env file: GROQ_API_KEY=your_key_here"
            )
        return instructor.from_groq(
            Groq(api_key=api_key),
            mode=instructor.Mode.JSON,
        )

    if provider == "openai":
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your .env file: OPENAI_API_KEY=your_key_here"
            )
        return instructor.from_openai(OpenAI(api_key=api_key))

    raise ValueError(
        f"Unknown LLM provider '{provider}'. Supported providers: 'groq', 'openai'."
    )
