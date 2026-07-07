# Round-3 doable-now work order (next-session spec)

> ## ⏳ Progress (updated 2026-07-07 — partial; resume in a fresh session)
>
> Four of the items are **done and merged** (trunk-based, self-merged green); one is **left**, one is
> **skipped**. The [`../CHANGELOG.md`](../CHANGELOG.md) "Round-3 doable-now sweep" section and
> [`outstanding-work.md`](outstanding-work.md) already reflect the merged items.
>
> | Item | Status | PR |
> |---|---|---|
> | **1 — accessibility contrast pass** | ✅ **DONE** | #135 |
> | **3 — base-image digest refresh** | ✅ **DONE** | #136 |
> | **2b — per-IP throttle** | ✅ **DONE** | #137 |
> | **2a — indexed `auth.users` lookup** | ✅ **DONE** (belt-and-suspenders: DB-first + Admin-API fallback) | #138 |
> | **2c — bound the shared limiter** | ☐ **LEFT — PAUSE FOR OWNER REVIEW** (shared cost-guard code) | — |
> | **4 — `proficiency_cefr_band` metric** | ⊘ **SKIPPED** (see note) | — |
>
> **What's left to do (next session):**
> 1. **Item 2c — bound `InProcessRateLimiter`** (`apps/api/app/ratelimit.py`). One-shot distinct keys
>    (attacker-varied emails/IPs behind the round-3 per-email + per-IP deletion limiters) are only
>    reclaimed on *re-hit*, so they accumulate. Plan (ready to implement): add a `max_keys` ctor arg
>    (default ~100 000) and a `_sweep_expired(now)` that drops every **fully-expired** key (newest
>    timestamp already aged out of the window), invoked from `hit()` when `len(self._hits) > max_keys`.
>    It only drops expired keys, so **no active window is touched → `tests/quota/*` must not regress**.
>    Add a whitebox test in [`../apps/api/tests/quota/test_ratelimit.py`](../apps/api/tests/quota/test_ratelimit.py)
>    (style: `FakeClock`, `limiter._hits`) with a small `max_keys` proving the map bounds. **⚠ This
>    class is shared with the LLM cost guard — open the PR and PAUSE for owner review; do NOT
>    self-merge.** This closes DoS item (3) of the #131-review bullet in `outstanding-work.md`.
> 2. **Final PR** — once 2c is decided, **delete this file** (`planning/doable-now-round3.md`,
>    mirroring how `doable-now-round2.md` was removed in #128) and make sure the CHANGELOG notes 2c's
>    outcome + item 4 as skipped. After that all remaining work is **owner-only** (prod cutover,
>    Phase-5 live dashboards, mobile, store consoles, Phase-9) — stop and report, don't invent scope.
>
> **Why item 4 was skipped:** a `proficiency_cefr_band` metric is a *categorical* band (A1…C2) whose
> only meaningful shape is a per-user "latest band" distribution — another **process-local** gauge with
> the exact scale-out caveat already flagged for `active_users`/`signups_total`, and its usefulness can
> only be judged against the **live** CEFR dashboard panel (owner/Phase-5, which I can't see). Per this
> file's own "skip if it can't be meaningfully tested without the live backend" clause, it's deferred
> into the Phase-5 observability wiring (item B of `outstanding-work.md`) rather than shipped as a
> misleading counter. Re-open if the owner wants the panel lit up with the live backend available.
>
> **Notes for the resuming session:** local integration/e2e are un-runnable here (port 54322 is
> another project's Supabase) — **rely on CI**. Local gate = `ruff`/`ruff format`/`mypy` +
> `eslint`/`prettier`/`tsc` + `vitest` + offline `pytest -k "not integration"`. `pnpm` isn't on PATH
> (use `corepack pnpm …`); run `uv run --directory apps/api …`. **mypy must be run repo-wide** (`mypy .`),
> not file-scoped — a test-file `arg-type` slipped past a scoped run and reddened #138's lint job once.

**What this is.** The remaining **buildable, CI-verifiable, non-owner code work** after the Phase-8
compliance code slice (#130–#133) merged. Everything on the *launch path* is now owner-gated (prod
cutover, Phase-5 live dashboards, mobile, store consoles, Phase-9) — see
[`outstanding-work.md`](outstanding-work.md). The items below are **not launch-blocking**; they are
quality/hardening work worth doing while the owner cutover is pending. Run them as a trunk-based
sweep, exactly like the round-1 (#117–#124) and round-2 (#126–#128) sweeps.

**Scope guardrails — do NOT:** touch mobile/Capacitor, prod, secrets, migrations, or store consoles.
Everything here is code + tests proven by the per-PR CI gate.

**How to run.** Same protocol as prior sweeps (see [`../CLAUDE.md`](../CLAUDE.md)): trunk-based, **one
PR per item** (branch → PR → self-merge on green; CI is the verify), ≥80% coverage held, legacy
Streamlit app kept runnable. **Self-merge** low-risk green PRs; **pause for owner review** on the
shared cost-guard-limiter change (item 2c). Keep [`../CHANGELOG.md`](../CHANGELOG.md) +
[`outstanding-work.md`](outstanding-work.md) in step as items close, and **delete this file** in the
final PR (mirroring how `doable-now-round2.md` was removed in #128).

**Environment notes (learned this session):**
1. **Local integration/e2e are un-runnable here** — port 54322 is another project's Supabase, so a
   local `pytest` runs the *offline* subset only and a local Playwright run can't start. **Rely on
   CI** for backend integration + FakeLLM e2e. Your local gate is `ruff`/`ruff format`/`mypy` +
   `eslint`/`prettier`/`tsc` + `vitest` + the offline `pytest -k "not integration"` subset.
2. **`pnpm` is not on PATH** — use `corepack pnpm …` (or `npx pnpm …`). Run uv without `cd` via
   `uv run --directory apps/api …`.
3. **Watch for a concurrent session.** If HEAD moves unexpectedly, check `git reflog` for another
   session's commits/checkouts and surface it to the owner before continuing (it happened this
   session — PR #129 was merged by a parallel session mid-work).
4. **Regen discipline:** any API route/schema change requires `uv run --directory apps/api python
   scripts/dump_openapi.py` **and** `corepack pnpm --filter api-types generate`, both committed, or
   the lint + `test_openapi_stable` jobs fail. (A late docstring edit on a handler counts — the
   docstring is the OpenAPI operation description.)

Suggested order by value/risk: **1 (accessibility) → 3 (base-image) → 2 (deletion hardening) →
4 (metric).**

---

## 1. Accessibility contrast pass — PRIMARY, highest value

**Problem.** The advisory axe sweep added in #127 (`apps/web/e2e/a11y.spec.ts`,
`@axe-core/playwright`, `@a11y`-tagged, `E2E_STACK`-gated) flagged **serious `color-contrast`
violations on every authenticated surface** (Dashboard / Generate / Review / Discover / Settings). It
only logs + attaches `axe-<screen>.json` — it never asserts — so it is not a merge gate. This is the
post-v1 "accessibility pass" backlog item (`outstanding-work.md` section (G)).

**Goal.** Bring text + UI-component contrast to **WCAG 2.1 AA** (4.5:1 normal text, 3:1 large text and
UI components) across the authenticated surfaces, **without regressing the Apple-HIG redesign** (iOS
blue primary, tinted rating pills, muted-foreground hierarchy) — in **both light and dark** themes.

**Approach.**
- Read the specifics from the CI advisory run's attached `axe-<screen>.json` (the `e2e` job's
  `@a11y` run) — that lists the exact failing nodes + color pairs. Don't guess.
- The violations are almost certainly in the **design-system color tokens** (the Tailwind config +
  the `hig-*` / `text-muted-foreground` / rating-pill token layer under `apps/web/src`), not
  one-offs — muted-foreground text on card backgrounds, tinted pills, and secondary text are the
  usual culprits. Fix at the **token level** so one change lifts many surfaces; fall back to
  per-component classes only where a token can't move without breaking the palette.
- Preserve the identity: nudge lightness/opacity to hit the ratio, don't recolor. Verify **light and
  dark** separately.
- **Flip the a11y spec from advisory to asserting** zero *serious* `color-contrast` violations on the
  swept surfaces once fixed (keep it `E2E_STACK`-gated). If a few unavoidable ones remain, assert a
  small documented allowlist and record the residue in the CHANGELOG.

**Verify.** `apps/web/e2e/a11y.spec.ts` reports zero serious color-contrast violations (now
asserting, not just logging); `vitest` + `eslint` + `prettier` + `tsc` + web build green; a visual
check (or a Playwright screenshot baseline of Review + Dashboard in both themes) confirms the redesign
is intact.

**Risk.** Medium — token changes ripple across the whole UI. Verify light + dark and the redesigned
surfaces (Review rating pills, Dashboard tiles, Generate save bar). Self-merge when green.

**Files.** `apps/web/tailwind.config.*` + the global CSS token layer, the swept page/components,
`apps/web/e2e/a11y.spec.ts`.

---

## 2. Public account-deletion DoS hardening — SECONDARY (low/latent, from the #131 review)

The 6-vector adversarial review of `POST /account/deletion-request` (#131) confirmed the security
invariants hold (no unauthorized delete / token forgery / body-enumeration; correct cascade). These
three residual **low, latent** items were deferred (safe at the current <200-user scale — 1:1
amplification today). See the "Public deletion endpoint — DoS hardening" bullet in
[`outstanding-work.md`](outstanding-work.md).

- **2a — indexed email lookup.** Replace the O(N) GoTrue admin *list-users* pagination in
  `AccountDeletionService.find_auth_user_id_by_email` (`apps/api/app/services/account.py`) with an
  **indexed** lookup — either a direct `SELECT id FROM auth.users WHERE lower(email) = lower(:email)`
  via a privileged session (⚠ **first confirm the app DB role has `SELECT` on `auth.users`** — the
  `get_usage_db` owner role likely does; prove it in a test), or GoTrue's get-user-by-email if the
  pinned version supports it. Removes the unauthenticated-endpoint → Admin-API fan-out. Note the unit
  tests currently drive the admin API via `httpx.MockTransport`; a DB query moves that coverage into
  the integration test. **Self-merge if clean.**
- **2b — per-IP throttle.** Add a per-IP (and/or global) rate limit to `POST
  /account/deletion-request` (`apps/api/app/routers/account_deletion.py`) — extract the client IP from
  `request.client.host` + `X-Forwarded-For` (Cloud Run sets it). Today only a per-email cap exists,
  which distinct-email floods bypass. **Self-merge if clean.**
- **2c — bound the shared limiter.** `InProcessRateLimiter` (`apps/api/app/ratelimit.py`) only
  reclaims a key's entry on *re-hit*, so one-shot distinct keys accumulate. Cap the map size or add a
  TTL sweep. ⚠ **This class is shared with the LLM cost guard** — do NOT regress `tests/quota/*`.
  **Pause for owner review** before merging this one (security/cost-guard code).

**Verify.** New/updated unit + integration tests; the #131 request→confirm→cascade integration test
still passes; **all `tests/quota/*` pass** (for 2c); ≥80% coverage held.

**Risk.** 2a — DB-grant uncertainty (test it first); 2b — low; 2c — shared cost-guard code (pause).

---

## 3. Base-image digest pin refresh — TRIVIAL

Bump the pinned `python:3.12-slim` **digest** in [`../apps/api/Dockerfile`](../apps/api/Dockerfile) to
the current one (the pin drifts; noted in `outstanding-work.md` tech-debt). **Verify:** the `build` CI
job (image build + `/health` smoke) is green. Self-merge. *(Optional; low value — do only if quick.)*

---

## 4. `proficiency_cefr_band` metric — OPTIONAL (observability)

Add the `proficiency_cefr_band` metric so the CEFR dashboard panel can light up (observability
follow-up in `outstanding-work.md`). Code + a unit test; the panel itself only renders against the
live backend (owner/Phase-5), so this is code-only prep. **Verify:** the metric is emitted +
unit-tested; ≥80% coverage. Self-merge. *(Skip if it can't be meaningfully tested without the live
backend.)*

---

**When the sweep is done:** record each merged PR in [`../CHANGELOG.md`](../CHANGELOG.md), tick the
matching lines in [`outstanding-work.md`](outstanding-work.md), and **delete this file** in the final
PR. After that, all remaining work is **owner-only** (prod cutover, Phase-5 live dashboards, mobile,
store consoles, Phase-9) — a fresh session should **stop and report** rather than invent scope.
