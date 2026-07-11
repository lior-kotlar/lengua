"""The single LLM key-resolution chokepoint (task 3.9 — the BYOK seam, DESIGN ONLY).

:func:`resolve_llm_key` is the **only** place in the codebase that reads a provider's operator API
key from the environment. Every provider obtains its key through it (``GroqProvider.from_env`` /
``GeminiProvider.from_env`` call it), so there is exactly one seam a future "bring your own key"
(BYOK) path would hook into — and a grep proves no other module reads ``GROQ_API_KEY`` /
``GEMINI_API_KEY`` directly (``tests/llm/test_key_resolution.py``).

Today it **always** returns the operator key from the environment for the active provider; the
``user`` parameter exists purely as the future override point and is **ignored**. No BYOK feature is
built here: no key storage, no UI, no new ``profiles`` columns, no per-user branching.

---

## BYOK design note (task 3.9.2 — how the seam would be used later; NOT implemented)

The growth escape hatch (see the root ``CHANGELOG.md`` locked decisions): let a paid user spend
their *own* provider key so heavy usage doesn't cost the operator. The plug-in points:

* **Key resolution.** A real implementation branches inside :func:`resolve_llm_key` on the
  ``user`` handle's ``profiles.plan`` (and a stored, encrypted per-user key): for a BYOK/paid plan
  it returns *that user's* key; for everyone else it falls through to today's operator key. The
  call sites (the providers) do not change — they already ask this one function for the key. The
  ``user`` would be passed down from the app layer (``app.deps.get_llm_provider`` would build a
  per-request provider keyed to ``current_user``); ``lengua_core`` stays DB-free, so the handle is a
  small structural :class:`KeyUser` (carrying ``plan``), never a DB query — the actual encrypted-key
  lookup is an app-layer concern injected behind this same function.
* **Cost guard.** A BYOK user spends their own quota, so the per-user daily caps and the global
  ``llm_budget`` kill-switch (``app.quota``) would **skip** them: the gate chain would check
  ``profiles.plan`` (BYOK ⇒ bypass the daily-cap, rate-limit and global-budget gates, since those
  exist only to protect the *operator* key) while still keeping the email-verified gate. Their usage
  could be metered separately for the user's own visibility, but never counts against the shared
  ``GLOBAL_DAILY_BUDGET``.

To actually build BYOK later you would add: encrypted per-user key storage (a new column/table +
envelope encryption), a settings UI to enter/rotate the key, the ``profiles.plan`` branch above, and
the cost-guard bypass — all behind this unchanged seam. None of that exists today.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

#: Active-provider name → the environment variable holding its operator API key. The **only** place
#: these env-var names are read; keep it that way (a grep test enforces it).
_OPERATOR_KEY_ENV: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@runtime_checkable
class KeyUser(Protocol):
    """The (future) per-user handle a BYOK key override would branch on — **inert today**.

    Kept a small structural :class:`typing.Protocol` exposing just the user's ``profiles.plan`` (the
    future branch key) so the app layer can pass any object carrying it without ``lengua_core``
    importing the DB models or running a query. :func:`resolve_llm_key` ignores it entirely for now
    (the operator key serves everyone).
    """

    plan: str


def resolve_llm_key(user: KeyUser | None = None, *, provider: str | None = None) -> str:
    """Return the API key the LLM client should use — today **always** the operator env key.

    ``provider`` selects which operator key to read (defaults to the active ``LLM_PROVIDER``); the
    providers pass their own name explicitly so e.g. ``GeminiProvider.from_env()`` always resolves
    ``GEMINI_API_KEY`` regardless of ``LLM_PROVIDER``. ``user`` is the future BYOK override point
    and is **ignored** today (the operator key is used for every user). Raises
    :class:`RuntimeError` if the selected provider's key is unset (fail-fast on the first
    LLM-dependent request — providers are constructed per-request, not at process boot), and
    :class:`ValueError` for a provider with no configured operator key.
    """
    # ``user`` is intentionally unused: today the operator key serves everyone. A future BYOK
    # implementation branches here on ``user.plan`` (see the module's design note) — the providers
    # never change because they already obtain the key only through this one function.
    name = (provider or os.getenv("LLM_PROVIDER", "groq")).strip().lower()
    env_var = _OPERATOR_KEY_ENV.get(name)
    if env_var is None:
        raise ValueError(
            f"No operator key is configured for LLM provider {name!r}; "
            f"expected one of: {', '.join(sorted(_OPERATOR_KEY_ENV))}."
        )
    key = os.getenv(env_var)
    if not key:
        raise RuntimeError(
            f"{env_var} is not set but the active LLM provider is {name!r}. "
            f"Set {env_var}, or use LLM_PROVIDER=fake for tests."
        )
    return key
