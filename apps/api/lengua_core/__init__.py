"""Lengua's pure domain core.

``lengua_core`` holds the framework- and storage-agnostic domain logic (LLM seam,
FSRS scheduling, proficiency scoring, card building, prompts, and the shared Pydantic
models). It imports **no** web framework and **no** database driver, so it stays
unit-testable and is shared by the FastAPI service (``app/``) and the legacy Streamlit
app (``legacy_streamlit/``) alike.

The structured-output models are re-exported here so callers have a single, stable
import surface (``from lengua_core import GeneratedCard, WordNote``).
"""

from __future__ import annotations

from .models import GeneratedCard, WordNote

__all__ = ["GeneratedCard", "WordNote"]
