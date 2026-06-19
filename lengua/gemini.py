"""Gemini wrapper: turn a list of vocabulary words into example sentences.

The fixed rules prompt + generation instruction + target language are attached
automatically here, so callers only supply the words.
"""
from google import genai
from google.genai import types

from . import config
from .models import GeneratedCard
from .prompts import system_instruction

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set (check your .env file).")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def generate_cards(
    words: list[str], language: str, vowelized: bool = False
) -> list[GeneratedCard]:
    """Generate example sentences in `language` that use the given vocabulary words.

    When `vowelized`, sentences come back fully vocalized (harakat / nikkud).
    """
    words = [w.strip() for w in words if w.strip()]
    if not words:
        return []

    resp = _get_client().models.generate_content(
        model=config.MODEL,
        contents="Vocabulary words:\n" + "\n".join(f"- {w}" for w in words),
        config=types.GenerateContentConfig(
            system_instruction=system_instruction(language, vowelized=vowelized),
            response_mime_type="application/json",
            response_schema=list[GeneratedCard],
        ),
    )
    return resp.parsed or []
