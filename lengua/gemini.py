"""Gemini wrapper: turn a list of vocabulary words into example sentences.

The fixed rules prompt + generation instruction + target language are attached
automatically here, so callers only supply the words.
"""
import time

from google import genai
from google.genai import errors, types

from . import config
from .models import GeneratedCard
from .prompts import system_instruction

# Backoff between retries when the model is transiently overloaded (503/429).
_RETRY_DELAYS = (1, 2, 4)

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


def explain_word(word: str, sentence: str, translation: str, language: str) -> str:
    """Return a 2-3 sentence explanation of a word's meaning and role in the sentence."""
    prompt = (
        f'In the {language} sentence: "{sentence}"\n'
        f'(English: "{translation}")\n\n'
        f'Explain the word "{word}" in 2-3 sentences. '
        f'Describe its meaning and its grammatical role in this specific sentence. '
        f'Be concise — no more than 3 sentences total.'
    )
    cfg = types.GenerateContentConfig(
        max_output_tokens=300,
        # Disable "thinking" so the small token budget isn't spent before any
        # answer text is produced (gemini-2.5-* think by default).
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    last_exc: Exception | None = None
    for delay in (0, *_RETRY_DELAYS):
        if delay:
            time.sleep(delay)  # the model was busy; wait, then retry
        try:
            resp = _get_client().models.generate_content(
                model=config.MODEL, contents=prompt, config=cfg
            )
            text = (resp.text or "").strip()
            if text:
                return text
            last_exc = RuntimeError("the model returned an empty response")
        except errors.ServerError as exc:  # 5xx incl. 503 "overloaded" — transient
            last_exc = exc
        except errors.ClientError as exc:  # only 429 (rate limit) is worth retrying
            last_exc = exc
            if getattr(exc, "code", None) != 429:
                raise

    raise RuntimeError(
        f"Gemini is busy right now ({last_exc}). Please tap the word again in a moment."
    )
