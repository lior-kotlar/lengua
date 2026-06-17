"""Shared data models."""
from pydantic import BaseModel


class GeneratedCard(BaseModel):
    """One example sentence produced by Gemini.

    `sentence` is in the target language, `translation` is English, and
    `used_words` lists which vocabulary words the sentence uses.
    """

    sentence: str
    translation: str
    used_words: list[str]
