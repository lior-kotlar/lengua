"""Generate -> Save service (task 1.3.6).

This is the heart of the loop: turn vocabulary words into example sentences (via the configured
LLM provider) and persist them as flashcards. It orchestrates the *pure* ``lengua_core`` logic
(prompt-level/band selection, card building, fresh FSRS state) and the repositories, and emits no
SQL itself:

* :meth:`generate` looks up the language + the learner's current CEFR band, asks the provider for
  sentences, and builds the recognition + production card pair for each — returning the unsaved
  pair (each tagged with the ``gen_level`` it was generated at) so a router can preview them.
* :meth:`save` persists those built cards into the deck, giving each its own fresh FSRS state so
  the two directions schedule independently, then commits.

The provider is injected (the :class:`~lengua_core.llm.base.LLMProvider` seam), so tests pass a
deterministic stub and never touch the network.
"""

from __future__ import annotations

import dataclasses
import json
import unicodedata
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter, run_provider
from app.product_metrics import record_cards_created
from app.repositories.cards import CardsRepository, NewCard
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError
from lengua_core import cards as core_cards
from lengua_core import proficiency, scheduler
from lengua_core.cards import BuiltCard, bare_word
from lengua_core.llm.base import LLMProvider

if TYPE_CHECKING:
    # Only for the type annotation: a runtime import of ``app.quota`` would form a cycle
    # (``app.quota`` → ``app.deps`` → ``app.services`` → this module). ``from __future__ import
    # annotations`` keeps the ``QuotaGuard`` annotation a string, so the guard is passed in (for its
    # observability span) without importing the class at runtime.
    from app.quota import QuotaGuard


def _fold(token: str) -> str:
    """Case- and diacritic-folded bare form of ``token`` for insensitive whole-word matching.

    Strips surrounding punctuation (:func:`~lengua_core.cards.bare_word`), decomposes to NFD and
    drops combining marks (so diacritics and Arabic vowel marks don't block a match), then
    case-folds — "Está", "esta", and "ESTÁ" all fold to ``esta``, and a vowelized surface matches
    its bare vocabulary word. Returns ``""`` for an all-punctuation token (never matched).
    """
    decomposed = unicodedata.normalize("NFD", bare_word(token))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _appears_as_run(sentence_tokens: list[str], needle: list[str]) -> bool:
    """True when ``needle`` occurs as a contiguous run of whole tokens in ``sentence_tokens``.

    Both are pre-folded token lists. A single-word ``needle`` reduces to whole-word membership; a
    multi-word phrase (e.g. ``["buenos", "dias"]``) must appear as adjacent tokens — so matching is
    word-boundary aware and never fires on a substring inside a larger word.
    """
    span = len(needle)
    if span == 0:
        return False
    return any(
        sentence_tokens[i : i + span] == needle for i in range(len(sentence_tokens) - span + 1)
    )


def _verified_used_words(used_words: list[str], sentence: str, vocab_folded: set[str]) -> list[str]:
    """Keep only ``used_words`` that are requested vocab AND actually occur in ``sentence`` (S7).

    The provider's ``used_words`` is advisory: a card can name a word that is missing from its own
    sentence, which overstates coverage — the Generate chips show it and Discover's ``known_words``
    is built from the saved ``used_words`` (so a phantom word would suppress that word as a future
    suggestion). We trust the sentence over the label: a word survives only when its folded bare
    form (case-/diacritic-insensitive) appears as a whole word — or contiguous phrase — in the
    sentence *and* was one of the words the user asked for. Original surface form and order are
    preserved; duplicates (by folded form) are dropped.
    """
    sentence_tokens = [_fold(tok) for tok in sentence.split()]
    kept: list[str] = []
    seen: set[str] = set()
    for word in used_words:
        folded = _fold(word)
        if not folded or folded in seen or folded not in vocab_folded:
            continue
        if _appears_as_run(sentence_tokens, [_fold(part) for part in word.split()]):
            kept.append(word)
            seen.add(folded)
    return kept


class GenerateService:
    """Generate example-sentence card pairs and save them to a user's deck."""

    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider | None = None,
        limiter: LLMConcurrencyLimiter | None = None,
    ) -> None:
        # ``provider`` is optional so a save-only caller (the cards router) need not construct a
        # real provider; :meth:`generate` requires one and fails fast if it was omitted. ``limiter``
        # bounds concurrent provider calls (3.5.1); it defaults to the process-wide singleton so
        # save-only callers don't need to pass one, and routers inject the (overridable) dependency.
        self._session = session
        self._provider = provider
        self._limiter = limiter if limiter is not None else get_llm_limiter()
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)
        self._proficiency = ProficiencyRepository(session)

    async def generate(
        self,
        user_id: uuid.UUID,
        language_id: int,
        words: list[str],
        guard: QuotaGuard | None = None,
    ) -> list[BuiltCard]:
        """Generate the recognition + production card pairs for ``words`` (unsaved).

        Raises :class:`NotFoundError` if the language is not the user's. The cards are tagged with
        the learner's current continuous score (``gen_level``) so later reviews only move the
        level for current-level material. When a ``guard`` is supplied (the request path passes one)
        its per-call observability span carries the ``llm.*`` attributes from the provider call.
        """
        provider = self._provider
        if provider is None:
            raise RuntimeError("GenerateService.generate requires an LLM provider.")

        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        score = await self._proficiency.get_score(user_id, language_id)
        band: str = proficiency.band_for_score(score)
        cleaned = [w.strip() for w in words if w.strip()]

        # Run the blocking provider call under the global concurrency cap (task 3.5.1): offloaded to
        # a thread so the event loop stays responsive, and bounded so we never overwhelm the free
        # tier. A persistent provider 429/5xx surfaces here as ``LLMTransientError`` → friendly 503.
        # ``run_provider`` also stamps the ``llm.*`` attributes (provider/model/latency/tokens/
        # input_size/retry_count) on the guard's span (tasks 3.8.1 / 5.2.1) and counts the consumed
        # tokens against ``llm_tokens_total`` (5.2.4). ``input_size`` for generate is the number of
        # vocabulary words sent to the model.
        generated = await run_provider(
            self._limiter,
            provider,
            guard.span if guard is not None else None,
            lambda: provider.generate_cards(
                cleaned, language.name, vowelized=language.vowelized, level_band=band
            ),
            input_size=len(cleaned),
            kind=guard.kind if guard is not None else None,
        )
        # Coverage guard (S7): the provider's ``used_words`` is advisory, so verify each one against
        # the sentence it claims to use and the words actually requested before it reaches a card.
        # The folded vocab set is built from ``cleaned`` (what we asked for); a phantom or
        # never-requested word is dropped so chips + ``known_words`` never overstate coverage.
        vocab_folded = {folded for w in cleaned if (folded := _fold(w))}
        built: list[BuiltCard] = []
        for card in generated:
            verified = _verified_used_words(card.used_words, card.sentence, vocab_folded)
            built.extend(
                dataclasses.replace(pair, used_words=verified)
                for pair in core_cards.build_cards(card, gen_level=score)
            )
        return built

    async def save(
        self, user_id: uuid.UUID, language_id: int, built: list[BuiltCard]
    ) -> list[Card]:
        """Persist built card pairs into the user's deck (``saved``, due now) and commit.

        Raises :class:`NotFoundError` if the language is not the user's.
        """
        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        rows: list[NewCard] = []
        for card in built:
            # Each card gets its own fresh FSRS state so the two directions schedule apart.
            state: tuple[str, str] = scheduler.new_card_state()
            fsrs_json, due_iso = state
            fsrs_state: dict[str, Any] = json.loads(fsrs_json)
            rows.append(
                NewCard(
                    front=card.front,
                    back=card.back,
                    direction=card.direction,
                    used_words=card.used_words,
                    word_explanations=card.word_explanations,
                    gen_level=card.gen_level,
                    saved=True,
                    fsrs_state=fsrs_state,
                    due=datetime.fromisoformat(due_iso),
                )
            )

        saved = await self._cards.save_cards(user_id, language_id, rows)
        await self._session.commit()
        record_cards_created(user_id, len(saved))  # product counter (task 5.2.5)
        return saved
