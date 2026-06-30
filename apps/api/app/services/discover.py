"""Discover service: suggest new vocabulary, then accept into the deck (task 1.3.6).

Two steps, mirroring the UX:

* :meth:`suggest` asks the provider for words at the learner's current CEFR band, excluding the
  vocabulary they already have saved cards for — a preview, nothing is persisted.
* :meth:`accept` feeds chosen words straight into the generate flow, so accepting suggestions
  produces real, saved cards.

It orchestrates the provider seam + repositories + the generate service, and emits no SQL itself.

**Cost guard (Phase 3.4 — count the billed call even if persistence fails).** ``accept`` makes a
real (billed) provider call and *then* persists. If the persist failed after the provider already
ran, a post-persist increment would skip — a billed call that bumped neither the global
``llm_budget`` nor the per-user ``llm_usage`` (and so dodged the cap/kill-switch). So, mirroring
``ExplainService``, when a :class:`~app.quota.QuotaGuard` is supplied (the request path always
passes one) ``accept`` records the spend **immediately after the successful provider call and before
``save``**. A ``save`` failure then still counts the call (the safe direction for a "never get a
bill" guard) and rolls the cards back; the increment commits on its own privileged usage session.

**Reuse cache (Phase 3.6.3 — cache-aware, like ``ExplainService``).** ``suggest`` first consults a
short-window in-process reuse cache (:mod:`app.discover_cache`). On a **hit** it returns the prior
preview with **no provider call and no gate/increment** — so the cap is enforced and counted only
when a real (billed) provider call actually happens (a cache **miss**). That is why the
``/discover`` route hands in an *unchecked* guard (``quota_guard("discover", enforce=False)``) and
``suggest`` runs :meth:`~app.quota.QuotaGuard.check`/``record_success`` itself on a miss, exactly as
``ExplainService`` does for its persisted ``word_explanations`` cache.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Card
from app.discover_cache import DiscoverCache, DiscoverKey, get_discover_cache
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter, run_provider
from app.repositories.cards import CardsRepository
from app.repositories.languages import LanguagesRepository
from app.repositories.proficiency import ProficiencyRepository
from app.services.errors import NotFoundError
from app.services.generate import GenerateService
from lengua_core import proficiency
from lengua_core.llm.base import LLMProvider

if TYPE_CHECKING:
    # Imported only for the type annotation. A runtime import would form a cycle: this module is
    # eagerly pulled in by ``app.services.__init__`` (which ``app.deps`` triggers), while
    # ``app.quota`` imports ``app.deps`` — so importing it here at runtime catches it half-built.
    # ``from __future__ import annotations`` keeps the ``QuotaGuard`` annotation a string, so the
    # TYPE_CHECKING-only import is enough (mirrors how ``ExplainService`` only works because the
    # explain router imports it lazily, after ``app.quota`` has finished loading).
    from app.quota import QuotaGuard


#: Extra candidate words to ask the provider for beyond the learner-facing ``count`` so that, after
#: dropping any already-known or duplicate suggestions a weak model may still surface (finding S15),
#: there are still enough genuinely-new words to fill ``count``. Kept small — the suggestion token
#: budget is modest and over-requesting only needs to absorb the occasional bad word, not double the
#: ask (``count`` itself is capped at 20 by the DTO, so the provider is never asked for many).
_SUGGEST_OVER_REQUEST = 5


def _dedup_unknown(words: list[str], known: list[str], *, count: int) -> list[str]:
    """Return up to ``count`` trimmed suggestions, dropping known or repeated words.

    Matching is **case-insensitive** on both axes — ``"Casa"`` is dropped when ``"casa"`` is already
    known, and ``"Agua"``/``"agua"`` collapse to a single entry — blank entries are skipped, and the
    first spelling of each kept word wins so the provider's ranking survives. This is the
    service-layer guard *behind* the generation prompt: the prompt merely *asks* the model to drop
    vocabulary the learner already has, and this *enforces* it (finding S15), trimming to ``count``
    only after the bad words are gone (so dropped words don't eat into the requested size).
    """
    if count <= 0:
        return []
    known_lower = {w.strip().lower() for w in known}
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        bare = word.strip()
        if not bare:
            continue
        lowered = bare.lower()
        if lowered in known_lower or lowered in seen:
            continue
        seen.add(lowered)
        result.append(bare)
        if len(result) >= count:
            break
    return result


class DiscoverService:
    """Suggest new words for a learner and turn accepted ones into cards."""

    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider,
        limiter: LLMConcurrencyLimiter | None = None,
        cache: DiscoverCache | None = None,
    ) -> None:
        self._provider = provider
        # Bound provider calls under the global concurrency cap (task 3.5.1); default to the
        # singleton and thread the same limiter into the generate flow ``accept`` delegates to.
        self._limiter = limiter if limiter is not None else get_llm_limiter()
        # Short-window preview reuse cache (task 3.6.3); default to the process-wide singleton.
        self._cache = cache if cache is not None else get_discover_cache()
        self._languages = LanguagesRepository(session)
        self._cards = CardsRepository(session)
        self._proficiency = ProficiencyRepository(session)
        self._generate = GenerateService(session, provider, self._limiter)

    async def suggest(
        self,
        user_id: uuid.UUID,
        language_id: int,
        *,
        count: int = 5,
        topic: str | None = None,
        fresh: bool = False,
        guard: QuotaGuard | None = None,
    ) -> list[str]:
        """Return up to ``count`` new words for the learner (excludes already-known vocabulary).

        Raises :class:`NotFoundError` if the language is not the user's.

        **Cache-aware (task 3.6.3).** A repeat for the same ``(user, language, topic, count)``
        within the reuse window is served from the in-process cache: no provider call, and — because
        no operator key was spent — no gate and no increment. The per-user daily ``discover`` cap is
        therefore enforced (via ``guard.check``) and counted (via ``guard.record_success``) **only
        on a cache miss**, the same cache-aware shape ``ExplainService`` uses. The language check
        runs first (and unconditionally) so an unknown language is a 404 even on a cache hit.

        **Reroll bypass + never-cache-empty (finding S8).** ``fresh=True`` is an *explicit reroll*:
        it skips the reuse lookup so an unchanged request returns a freshly generated (and so billed
        + counted) set rather than replaying the identical cached preview. And an **empty** preview
        is never cached — a transient "no words" must not pin emptiness for the whole window; the
        next request retries the provider.

        **Known-word + dedup guard (finding S15).** The provider is over-requested by a small
        buffer, then :func:`_dedup_unknown` drops anything the learner already knows (matched
        case-insensitively, not just via the prompt) and any duplicates before trimming to ``count``
        — defence in depth behind the generation prompt for weaker dev models.
        """
        language = await self._languages.get(user_id, language_id)
        if language is None:
            raise NotFoundError(f"Language {language_id} not found.")

        key = DiscoverKey(user_id=user_id, language_id=language_id, topic=topic, count=count)
        # A normal request reuses a fresh-enough preview (free: no provider call, no gate/count). An
        # explicit reroll (``fresh``) skips the lookup so it can't replay the identical words (S8).
        if not fresh:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        # Cache miss (or a forced reroll): this WILL call the provider, so gate the per-user daily
        # cap first (429 if at).
        if guard is not None:
            await guard.check()

        score = await self._proficiency.get_score(user_id, language_id)
        band: str = proficiency.band_for_score(score)
        known = await self._cards.known_words(user_id, language_id)
        # Over-request a small buffer (S15) so dropping known/duplicate words still leaves ``count``
        # genuinely-new ones. Blocking provider call under the global concurrency cap (3.5.1);
        # ``run_provider`` stamps the ``llm.*`` attributes on the guard's per-call span (3.8.1 /
        # 5.2.1) and counts tokens (5.2.4). ``input_size`` is the learner-facing requested count.
        provider_count = count + _SUGGEST_OVER_REQUEST
        raw: list[str] = await run_provider(
            self._limiter,
            self._provider,
            guard.span if guard is not None else None,
            lambda: self._provider.suggest_new_words(
                language.name, band, known, count=provider_count, topic=topic
            ),
            input_size=count,
            kind=guard.kind if guard is not None else None,
        )
        # Enforce the prompt's "exclude known vocabulary" instruction in code, dedup, trim (S15).
        suggestions = _dedup_unknown(raw, known, count=count)
        # Count the successful spend, then memoise the preview for the reuse window — but never
        # cache an *empty* preview (S8): the next request should retry, not be stuck on "no words".
        if guard is not None:
            await guard.record_success()
        if suggestions:
            self._cache.put(key, suggestions)
        return suggestions

    async def accept(
        self,
        user_id: uuid.UUID,
        language_id: int,
        words: list[str],
        guard: QuotaGuard | None = None,
    ) -> list[Card]:
        """Generate and save cards for accepted ``words`` (delegates to the generate flow).

        The provider runs inside :meth:`GenerateService.generate`; when a ``guard`` is supplied the
        spend is counted **right after** that successful provider call and **before** :meth:`save`,
        so a persistence failure still bills the (already-made) provider call rather than leaving a
        real call uncounted — the safe direction for the global kill-switch. The guard is also
        handed to :meth:`GenerateService.generate` so its per-call span carries the ``llm.*`` attrs.
        """
        built = await self._generate.generate(user_id, language_id, words, guard=guard)
        if guard is not None:
            await guard.record_success()
        return await self._generate.save(user_id, language_id, built)
