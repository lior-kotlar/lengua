"""LLM provider seam.

All generation goes through the :class:`LLMProvider` interface so the model behind it is
a config choice (``LLM_PROVIDER``), not a code change. Real impls (Groq default / Gemini
later) land in Phase 1; :class:`FakeLLM` is the deterministic stand-in for tests/CI.
"""

from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM

__all__ = ["FakeLLM", "LLMProvider"]
