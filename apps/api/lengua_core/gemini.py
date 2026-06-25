"""Gemini wrapper: turn a list of vocabulary words into example sentences.

The fixed rules prompt + generation instruction + target language are attached
automatically here, so callers only supply the words.
"""
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from .models import GeneratedCard
from .prompts import suggestion_instruction, system_instruction

# Load the legacy ``.env`` (repo root) so GEMINI_API_KEY / GEMINI_MODEL are available. The
# provider key + model are operator config read from the environment — never DB-stored secrets.
load_dotenv()

# Backoff between retries when the model is transiently overloaded (503/429).
_RETRY_DELAYS = (1, 2, 4)

_client: genai.Client | None = None


def _model() -> str:
    """The Gemini model id from the environment (default ``gemini-2.5-flash``)."""
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (check your .env file).")
        _client = genai.Client(api_key=api_key)
    return _client


def generate_cards(
    words: list[str],
    language: str,
    vowelized: bool = False,
    level_band: str | None = None,
) -> list[GeneratedCard]:
    """Generate example sentences in `language` that use the given vocabulary words.

    When `vowelized`, sentences come back fully vocalized (harakat / nikkud). When
    `level_band` (a CEFR band like "A2") is given, sentence length and complexity are
    sized to the learner's level.
    """
    words = [w.strip() for w in words if w.strip()]
    if not words:
        return []

    resp = _get_client().models.generate_content(
        model=_model(),
        contents="Vocabulary words:\n" + "\n".join(f"- {w}" for w in words),
        config=types.GenerateContentConfig(
            system_instruction=system_instruction(
                language, vowelized=vowelized, level=level_band
            ),
            response_mime_type="application/json",
            response_schema=list[GeneratedCard],
        ),
    )
    return resp.parsed or []


def suggest_new_words(
    language: str,
    level_band: str,
    known_words: list[str],
    count: int = 5,
    topic: str | None = None,
) -> list[str]:
    """Ask Gemini to pick `count` new vocabulary words the user doesn't know yet.

    Returns a list of word strings. Gemini is told the learner's CEFR level, an
    optional topic, and the full list of known words to avoid.
    """
    resp = _get_client().models.generate_content(
        model=_model(),
        contents=f"Suggest {count} new {language} vocabulary words.",
        config=types.GenerateContentConfig(
            system_instruction=suggestion_instruction(
                language, level_band, known_words, count, topic
            ),
            response_mime_type="application/json",
            response_schema=list[str],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return resp.parsed or []


def explain_word(word: str, sentence: str, translation: str, language: str) -> str:
    """Return a short (≤ 2 sentence) explanation of a word's meaning and role.

    Trivial function words (e.g. "to", "in") get a one-word/short-phrase gloss.
    """
    prompt = (
        f'In the {language} sentence: "{sentence}"\n'
        f'(English: "{translation}")\n\n'
        f'Briefly explain the word "{word}": its meaning and its role in this sentence. '
        f'Use at most two sentences. If it is a very simple or common word '
        f'(e.g. "to", "in", "and"), a single word or short phrase is enough.'
    )
    cfg = types.GenerateContentConfig(
        max_output_tokens=150,
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
                model=_model(), contents=prompt, config=cfg
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
