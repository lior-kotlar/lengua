"""Shared data models for LLM-generated content.

Ported verbatim from the legacy ``lengua/models.py`` so the provider interface and its
fakes return exactly the shapes the rest of the app already expects.
"""

from pydantic import BaseModel


class WordNote(BaseModel):
    """A short explanation of one word in a generated sentence.

    ``word`` is the surface form exactly as it appears in the sentence (keep any
    diacritics), and ``note`` is a brief gloss — at most two sentences, or a single
    word/short phrase for trivial function words.
    """

    word: str
    note: str


class GeneratedCard(BaseModel):
    """One example sentence produced by an LLM provider.

    ``sentence`` is in the target language, ``translation`` is English, and
    ``used_words`` lists which vocabulary words the sentence uses. ``word_notes``
    holds a short, tap-ready explanation for each meaningful word in ``sentence``.
    """

    sentence: str
    translation: str
    used_words: list[str]
    word_notes: list[WordNote] = []
