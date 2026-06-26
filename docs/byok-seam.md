# BYOK key-resolution seam (design note — Phase 3.9.2)

**Status: DESIGN ONLY. No BYOK feature is built.** This note records *how* a future
"bring your own key" (BYOK) capability would plug into the seam that already exists, so the
hook is in place now and the growth escape hatch (see
[`planning/08-open-questions-and-costs.md`](../planning/08-open-questions-and-costs.md)) is a
later, additive change — not a rewrite. Nothing here is implemented: there is **no** key storage,
**no** UI, **no** new `profiles` columns, and **no** per-user key branching today.

## What exists today (the seam)

`resolve_llm_key(user)` in
[`apps/api/lengua_core/llm/keys.py`](../apps/api/lengua_core/llm/keys.py) is the **single
chokepoint** that turns a request into the API key the LLM client uses. Today it **always** returns
the operator key from the environment (`GROQ_API_KEY` / `GEMINI_API_KEY`, selected by
`LLM_PROVIDER`). Both real providers (`GroqProvider.from_env` / `GeminiProvider.from_env`) obtain
their key **only** through it — no other module reads the key env vars (enforced by
`tests/llm/test_key_resolution.py`). The `user` parameter is the future override point and is
**ignored** today; it is a small structural `KeyUser` handle (carrying `profiles.plan`), never a DB
query, so `lengua_core` stays database-free.

## How a per-user key would plug in later

1. **Key resolution branches in `resolve_llm_key`.** A real implementation inspects the `user`
   handle's **`profiles.plan`**: for a BYOK / paid plan it returns *that user's* stored key;
   everyone else falls through to today's operator key. The call sites (the providers) do **not**
   change — they already ask this one function for the key. The app layer would pass the
   authenticated `current_user` down (`app.deps.get_llm_provider` building a per-request provider
   keyed to the user), and the actual encrypted-key lookup would be injected behind this same
   function so `lengua_core` never touches the DB.

2. **The cost guard skips a BYOK user.** A BYOK user spends *their own* quota, so the per-user daily
   caps, the per-user rate limit, and the global `llm_budget` kill-switch in
   [`apps/api/app/quota.py`](../apps/api/app/quota.py) exist only to protect the **operator** key and
   would be **bypassed** for them. Concretely, `QuotaGuard.check` would read **`profiles.plan`** and,
   for a BYOK plan, skip the rate-limit, daily-cap, and global-budget gates (still keeping the
   email-verified gate). Their usage would never count against the shared `GLOBAL_DAILY_BUDGET`
   (`llm_budget`); it could be metered separately purely for the user's own visibility.

## What building BYOK would still require (not done here)

- Encrypted per-user key **storage** (a new column/table + envelope encryption / a secrets manager).
- A settings **UI** to enter / rotate / remove the key.
- The **`profiles.plan` branch** in `resolve_llm_key` (point 1) and the cost-guard **bypass**
  (point 2).
- Tests for the BYOK path, key redaction in logs, and revocation.

All of the above sit **behind the unchanged seam**, which is the entire point of landing
`resolve_llm_key` now.
