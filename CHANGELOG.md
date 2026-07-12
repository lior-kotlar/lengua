# Changelog

The durable record of what shipped as Lengua was rebuilt from a local single-user
Streamlit app into a deployed, multi-user product (FastAPI + React + Supabase + Cloud Run).
This is the source of truth for **what is done**; open work lives in
[`planning/outstanding-work.md`](planning/outstanding-work.md) and the owner launch runbook
[`planning/go-live-activation.md`](planning/go-live-activation.md).

> The productionization ran trunk-based, one PR per task, in phase order (PRs #1 → #114), so the
> PR ranges below map to phases by merge order (the top-of-log post-close-out sections carry the
> later PR refs).
> Milestones: **M1** = backend loop over HTTP;
> **M2** = multi-user (auth + RLS) with the LLM cost guard armed; **M3** = React web app at full
> parity; **M4** = deployed to staging **and** prod (staging leg live; prod leg = owner cutover).

---

## 2026-07-12 — Post-audit verification sweep: two fixes shipped, one PR opened, docs re-synced

A second full verification (after the 2026-07-11 audit) re-checked every claim the six post-audit
merges #153–#158 introduced — ~60 agents, adversarial refutation on every finding; report:
[`planning/verification-2026-07-12.md`](planning/verification-2026-07-12.md). All shipped claims
held; the sweep's own output:

- **Vowel-marks toggle a11y fix (PR #160).** #158's language-aware visible label had left the old
  hardcoded `aria-label="Show vowel marks"` behind — the accessible name no longer contained the
  visible label (WCAG 2.5.3 "label in name"). A new `vowelMarksLabel()`
  (`apps/web/src/lib/language-text.ts`) now drives **both** strings; label-in-name tests
  (nikkud + harakat) added, proven to fail on the old code.
- **CI guard for the "keep legacy Streamlit runnable" contract (PR #161).** The standing CLAUDE.md
  rule had zero automated coverage. A new import-smoke (`apps/api/scripts/legacy_smoke.py`, run in
  CI via `uv run --with streamlit` — streamlit stays out of the project deps) imports the legacy
  support modules, executes the four pages' AST-extracted top-level imports (page *bodies* need a
  real Streamlit runtime, deliberately not run), `compileall`s the pages, and exercises the prompt
  builders under the no-store default. Proven to fail on a sabotaged symbol.
- **Prompt-store render-guard broadening ([PR #159](https://github.com/lior-kotlar/lengua/pull/159)
  — open, awaiting owner merge).** The #153 guard caught only `(KeyError, IndexError, ValueError)`;
  `{language.foo}` (AttributeError) / `{language[foo]}` (TypeError) overrides still 500'd every
  generation. Guard → `except Exception` + two new test cases. Owner-review class, like #153.
- **Docs re-sync** (same PR as this entry): the #150 CHANGELOG heading un-staled ("awaiting owner
  review" → merged `de1ecc4`); the missing #158 entry added below; `provider.py` module docstring
  aligned with the A4 per-request wording; `prompt_store.py`/`test_prompt_store.py` pin-path
  leftovers removed; parity ledger rows 33/35 + §6 rewritten for #95/#158; branch-protection JSON
  in `owner-deferred-tasks.md` now uses the real check names; `phase-task-runner.md` merge command
  → `--squash`; dead spec citation de-linked; board/tracker/status blocks synced. Post-v1 backlog
  gained two marginal custom-path notes (Unicode case-folding; case-insensitive unique index —
  migration-gated).

## 2026-07-11 — Language-aware vowel-marks option (#158)

A direct feature PR (no tracking issue) that merged **after** the 2026-07-11 audit's final docs
sync, so it is recorded here retroactively (2026-07-12, by the post-audit verification sweep).
Frontend-only; self-merged on green CI.

- **Script-specific vowel-mark terms.** The add-language flow and the display toggle now name the
  marks by the active script — **harakat** (Arabic script) / **nikkud** (Hebrew script) — via new
  `vowelMarkTerm()` / `isVowelizableCode()` helpers in `apps/web/src/lib/language-text.ts`, with the
  generic "vowel marks" fallback for an unrecognised vowelized code.
- **Custom-path checkbox is now gated.** In the custom (experimental) add-language path, the
  "Include vowel marks" checkbox renders only once the typed code resolves to an Arabic/Hebrew
  script (with a stale-`vowelized` reset when the code changes away) — a deliberate improvement
  over the legacy app's unconditional checkbox.
- **New `HelpTip` component** (`apps/web/src/components/help-tip.tsx`) — an accessible info-tip,
  first used to explain what vowel marks are on both the add form and the display toggle.
- README updated in the same PR. Distinct from the still-open §1.2 backlog item (UI-wiring the
  `vowelized` flag on an *existing* language); that item remains open.

## 2026-07-11 — Home-tile percent edge (#152 / #146)

Closes Track-1.1 [#152](https://github.com/lior-kotlar/lengua/issues/152), the last open code item in
the 2026-07-11 audit's §1.1 — a display-only rounding edge on the Dashboard language tiles. Frontend
only; self-merged on green CI (tiny, reversible).

- **"% to next" caption could read 100% before the band advanced.** `progressPercent`
  (`apps/web/src/lib/cefr.ts`) rounded the intra-band fraction, so a value ≥ 0.995 rendered
  "100% to B2" while the band chip on the same tile still said B1 — the backend only advances the band
  at the integer boundary (`band_progress` returns 1.0 solely at the absolute top C2, where the caption
  is hidden). Now a below-1 fraction that rounds up to 100 is held at **99**. Chosen cap-at-99 over a
  plain floor deliberately: a floor would shift `0.555 → 55` (breaking the existing `→ 56` case) and
  every other percentage; capping only the round-to-100 window changes nothing but the one-quantum band
  top, and an exact 1.0 still reads 100. Added ≥ 0.995 boundary tests (0.994 / 0.995 / 0.999 / 1.0);
  `cefr.ts` stays at 100% coverage. No backend, route, or schema change. **§1.1 now has no open code
  items.**

## 2026-07-11 — Language-picker follow-ups (#151 / #95)

Closes Track-1.1 [#151](https://github.com/lior-kotlar/lengua/issues/151), the four follow-ups the
2026-07-11 audit raised against the #95 curated language picker. Frontend + one small server fix;
self-merged on green CI (low-risk, reversible).

- **(a) Case-variant duplicate rows — fixed server-side.**
  `LanguagesRepository.get_by_name` now matches on `lower(name)` (via `func.lower`, portable across
  SQLite/Postgres) instead of an exact-string equality. The web picker already matched curated names
  case-insensitively, so a curated "French" pick over an existing "french" was inserting a second,
  case-variant language row. Both callers benefit: `add_language`'s idempotent-add dedupe and
  `update_language`'s rename-conflict guard now treat differently-cased spellings as the same
  language (a pure case change of a row's own name still resolves to itself, so re-casing is allowed).
  The server-side fix was chosen over a client pre-check as the single, robust point that covers
  every caller. Repo + service integration tests assert the case-insensitive dedupe and conflict.
- **(b) In-flight reset race — fixed.** `AddLanguageForm`'s "Change" (curated step) and "Back to
  list" (custom step) affordances are now disabled while the add is `isPending`, so a slow-network
  user can't navigate away between pressing "Add" and the success reset to the picker (which would
  clobber their view). Unit tests cover both locks.
- **(c) Curated-path e2e — added.** `apps/web/e2e/languages.spec.ts` gains a second spec that drives
  the **curated** pick→submit→remove flow (search "French" → pick the curated row → choose B1 →
  add → verify list/picker/band → remove). Every prior e2e drove only the custom fallback; this
  covers the feature's primary new path. Runs against the FakeLLM ephemeral stack in CI (no real LLM
  calls — none of these flows touch the LLM seam).
- **(d) Analytics `curated` flag — real provenance threaded.** `AddLanguageInput` gains a `curated`
  boolean set by the form (`true` from the curated step, `false` from the custom step), and
  `trackLanguageAdded` now reports that instead of a `findCurated(name)` name-table lookup. A custom
  add of a curated-named language (e.g. typing "Spanish" in the custom path) now correctly reads as
  `curated: false`, matching the event's documented picker-path-provenance semantics.

## 2026-07-11 — Prompt-store hardening (#80 follow-ups) · owner-approved and merged

Closes Track-1.1 [#150](https://github.com/lior-kotlar/lengua/issues/150) (the one HIGH audit
finding): the DB-backed prompt store's fail-safe covered **read** failures but not **render** or
**assembly** failures. Internal hardening of the generation-critical prompt path — **no API/route/
schema change** — in `apps/api/lengua_core/prompts.py` and `apps/api/app/prompt_store.py`. Opened
for owner review rather than self-merged (a fault here 500s every generation; #80 itself was
owner-reviewed), then **merged 2026-07-11 after the owner explicitly authorized it** (PR #153,
squash `de1ecc4`, CI green).

- **(a) Render guard.** Every DB-overridden fragment fed to `str.format(...)` is now wrapped in a
  try/except (`_render_fragment`): a malformed override — unknown `{placeholder}`, positional `{}`,
  stray unbalanced brace — is logged loudly and that **one** fragment falls back to its
  `CODE_DEFAULTS` text, instead of raising inside every generation request and 500-ing the whole app
  until the row is fixed. The `rules` block (no placeholders, may hold literal braces) is still
  appended verbatim, never `.format`-rendered. Code-default templates are rendered unguarded so a
  genuine code bug still surfaces in tests.
- **(b) Read-time validation.** `read_active_prompts_from_db` now sanitises the snapshot via
  `_validate_snapshot`: rows whose key isn't in `PROMPT_KEYS` are dropped (they can never resolve),
  and **empty-string** overrides are dropped so `''` can't silently blank a fragment (e.g. an empty
  `output_format` deleting the whole output-shape instruction). Both warn.
- **(c) End-to-end wiring test.** A new `@pytest.mark.integration` test boots `create_app` with a
  non-empty in-memory store installed (deliberately overriding the autouse empty offline-store
  fixture), drives a real `POST /generate`, and — via a spy provider that assembles the true
  `system_instruction` — asserts the DB override reached the assembled system prompt. Proves the
  install → warm → snapshot-capture → render chain a silent wiring regression would otherwise hide.
- **(d) Torn-assembly race fixed.** A single prompt build resolved 2–4 fragments, each re-reading a
  snapshot a concurrent `warm()` could swap mid-build (mixing two prompt versions in one request).
  Builds now capture the **whole** active map once via a new `PromptStore.snapshot()` hook (installed
  alongside the per-key `get`), cached as a read-only `MappingProxyType`; every fragment in that
  build resolves from the one frozen map.
- **(e) Version-pinning path trimmed.** `resolve(version>0)` / `read_pinned_prompt_from_db` /
  `_SELECT_PINNED` / the `ACTIVE_VERSION` sentinel / the `pinned_reader` ctor arg had **zero
  production callers** (the advertised reproducibility/A-B path was unreachable). Trimmed — the
  lower-risk choice vs wiring a new request-param/feature-flag with no product owner — and the module
  docstring + `apps/api/README.md` corrected: generation resolves only the **active** version;
  rollback is still an `is_active` flip over the append-only history.
- **(f) intentionally skipped.** A DB `CHECK (content <> '')` / key-enum constraint is
  migration-gated and left for the owner per protocol; (b) already covers it at read time.
- **Tests.** `lengua_core/prompts.py` and `app/prompt_store.py` are at 100% line+branch from the
  offline unit suite; the pinning-path tests were removed and render-guard / validation / snapshot /
  wiring tests added. Backend gate held.

## 2026-07-10 — Home language cards: explicit "% to next level" + due/new breakdown

Closes Track-1.1 [#146](https://github.com/lior-kotlar/lengua/issues/146) (PR #148, squash
`a9344c8`) — the two remaining
gaps in the Dashboard's per-language tiles (`apps/web/src/components/dashboard/language-tiles.tsx`).
**Frontend-only** — zero backend/API/schema diff; all data was already served by the existing
`GET /review/due` + `GET /proficiency/{id}` fan-out (`src/lib/dashboard.ts`). No layout changes
(the Today hero, quick actions, and Word of the Day are untouched).

- **Explicit "what's left to the next level."** The progress-bar footnote gained the exact percent:
  it now reads **`62% to B2`** (the percent is the existing `progressPercent(progress)` from
  `src/lib/cefr.ts`, rendered in a `tabular-nums` span so the digits don't jitter). The top band
  keeps **"Top level (C2)"**, and an unknown level still hides the bar + caption entirely.
- **Per-tile due/new breakdown.** The due badge now uses the same copy the Today hero already
  shows — **`{due} due · {fresh} new`** (orange) when cards await — instead of the opaque
  `{n} ready`, so a language's tile and hero read identically. **`Done`** (green) at zero, the
  loading skeleton, and the errored "—" dash are unchanged.
- **Tests.** New co-located `language-tiles.test.tsx` unit-tests the caption (rounded percent,
  C2 top-level, unknown-level hidden) and every badge state (breakdown / Done / error dash /
  loading), plus the unchanged link/route/active-chip contract; the `Dashboard.test.tsx` tile
  assertions were updated to the new copy. The `cefr` helpers this relies on
  (`progressPercent` / `nextBand`) were already fully unit-tested. Web coverage stays ≥ 80%
  (99.76% line / 98.47% branch overall).

## 2026-07-09 — Curated language picker + custom (experimental) fallback

Closes Track-1.1 [#95](https://github.com/lior-kotlar/lengua/issues/95) — replace the free-text
Name/Code entry on the web **Add a language** form with a searchable **curated picker**, keeping a
free-form fallback for anything off the list. **Frontend-only** (Option B; the full spec lived in
`planning/language-support-design.md`, retired post-ship — git history retains it) — zero backend/API/schema/migration diff; the legacy
Streamlit app is untouched, and the create call still posts the same `{name, code, vowelized}`.

- **Curated list as the single source of truth (`apps/web/src/lib/curated-languages.ts`).** A typed
  readonly table of 44 languages (`name` / `nativeName` endonym / `code` / `script` / `vowelizable`)
  — the CEFR-taught European canon plus the major world languages the model handles confidently.
  `rtl` is deliberately NOT duplicated: direction + script font stay derived from the `code` by the
  existing `language-text.ts` (`directionForCode` / `scriptFontClass`); `script` is carried for
  future font work but never persisted. Helpers `findCurated(name)` (case-insensitive, trimmed) and
  `findCuratedByCode(code)` (primary-subtag match). Invariant tests assert unique/lowercase codes,
  unique names, `vowelizable ⊆ {ar, he, fa}`, and every Arabic/Hebrew-script entry is RTL.
- **ARIA combobox (`apps/web/src/components/language-combobox.tsx`).** A search input
  (`role="combobox"`, `aria-expanded`/`aria-controls`/`aria-activedescendant`) over a `role="listbox"`;
  case-insensitive substring filter on name/endonym/code, full list on empty query, scrollable
  max-height, endonym shown as muted secondary text in its own script (`scriptFontClass`) so each
  row doubles as a script preview. Keyboard ↑/↓/Enter/Esc. The last row is always
  `Add "<query>" as a custom language…` (the only row when nothing matches).
- **Picker-first add form (`add-language-form.tsx`).** Choosing a curated language shows NO Name/Code
  inputs (a chip with a Change affordance) + Starting level + — only when `vowelizable` — a
  vowel-marks toggle **defaulted ON** (fixes #95 pain point 3: a beginner adding Arabic gets harakat
  without opting in). The custom path keeps today's free-form fields (Name prefilled from the query,
  optional Code, level, vowel checkbox with the existing S14 "code required when vowelized"
  validation) under a **"Custom (experimental)"** heading with a coverage footnote; typing a code
  whose primary subtag matches a curated entry pre-sets the vowel default, and a soft, non-blocking
  hint warns when another of the user's languages already uses that code's subtag. A back affordance
  returns to the picker.
- **"Experimental" badge (`pages/Languages.tsx`).** A small muted badge on any language whose `name`
  has no case-insensitive curated match — derived client-side (name-based, since generation
  interpolates the name), so existing rows need no backfill.
- **Analytics.** `trackLanguageAdded` now also carries a non-PII `curated: boolean` alongside the
  language code (asserted PII-free in `analytics-events.test.ts`).
- **E2E sweep.** The Playwright specs that drive the add form (`e2e/languages.spec.ts`,
  `e2e-staging/{full-flow,fresh-user-lifecycle}.spec.ts`) now go through the custom path for their
  timestamp-unique throwaway languages. Web unit coverage held ≥80% (full suite green).

## 2026-07-09 — Move LLM prompts to the database with versioning (PR #143, merged)

Closes Track-1.1 [#80](https://github.com/lior-kotlar/lengua/issues/80) — move the LLM prompt
fragments out of the codebase and into the DB **with versioning**, so a prompt can be tweaked (or
rolled back) in production **without a code change + redeploy**, keeping full history. The PR was
paused for owner review per protocol (architectural: a new DB-backed prompt store + a dual
migration), then **owner-approved and merged 2026-07-09** (squash `17facfe`, CI 10/10 green).

- **New `public.prompt_versions` table (dual migration).** Append-only, keyed by a logical `key`
  per fragment (`rules`, `generation_instruction`, `vocalization_instruction`, `level_instruction`,
  `output_format`, `suggestion_instruction`); `(key, version)` unique, a **partial unique index**
  (`WHERE is_active`) enforcing at most one active version per key, plus `content` / `note` /
  `created_at` / `created_by`. Seeded with the current in-code prompt text as **version 1
  (active)** for each key. Canonical Supabase SQL
  (`supabase/migrations/20260709000000_prompt_versions.sql`) + a semantically-identical Alembic
  migration (`migrations/versions/20260709_0007_prompt_versions.py`, `to_regrole`-guarded so it
  round-trips on bare Postgres). **Locked down like `feature_flags`/`llm_budget`:** `REVOKE ALL …
  FROM authenticated, anon` + deny-by-default RLS (no policy) — prompts are global operator config,
  server-read-only, never reachable by a client.
- **New prompt store (`apps/api/app/prompt_store.py`).** Reads the **active** version per key on a
  privileged, RLS-bypassing app session, caches the snapshot for `PROMPT_CACHE_TTL_SECONDS`
  (default 60s, injectable clock) so a change is picked up within one TTL — no redeploy. `resolve()`
  supports the `-1` sentinel (→ active) and a positive pinned version (reproducibility / A-B).
  <!-- The pinned-version path had zero callers and was trimmed on 2026-07-11 (#150); generation
  resolves only the active version. -->
  Fails safe to the in-code defaults when the table is empty/unreachable.
- **Refactored builders keep assembly in code (`lengua_core/prompts.py`).** `system_instruction` /
  `suggestion_instruction` now source each fragment's **text** via a synchronous, injectable source
  hook (DB override → cached snapshot, else the code constant), while all assembly + placeholder
  interpolation stays in code. Builder signatures are unchanged, so the **legacy Streamlit app** and
  the **CI/E2E FakeLLM path** keep working against the code constants with **zero DB dependency**.
  The store's snapshot is refreshed on the event loop in `app.llm_runner.run_provider` (the single
  async chokepoint) *before* the blocking provider call is offloaded to its worker thread, so the
  synchronous builders read a materialised snapshot without ever awaiting.
- **Tests (offline unit + DB integration).** Source-hook fallback + override; store warm/get, the
  TTL cache + change-without-redeploy refresh (injected clock), TTL floor, invalidate,
  concurrent-warm-once, `resolve` active + pinned + fallbacks; DB reader mapping + fail-safe; a
  seed round-trip asserting the seeded rows equal the in-code defaults; the acceptance path (a new
  active version changes resolution with no redeploy); and the SECURITY lockdown (RLS deny-by-default
  + `authenticated`/`anon` denied at runtime), plus an Alembic-0007 lockstep regression. Full local
  gate green (ruff, ruff-format, mypy repo-wide, offline pytest); DB-backed integration + the
  Alembic drift check run in CI.

## 2026-07-08 — Show/hide ("eye") toggle on every password input

Closes Track-1.1 [#99](https://github.com/lior-kotlar/lengua/issues/99) — a frontend-only
affordance so a user can check what they typed.

- **New reusable `PasswordInput`** (`apps/web/src/components/ui/password-input.tsx`) renders the
  shared `Input` inside a `relative` wrapper with a `ghost`/`icon` eye button
  (`lucide-react` `Eye`/`EyeOff`) absolutely positioned on the right; the input gets right padding so
  revealed text never sits under the icon. One source of truth (`show`) drives
  `type={show ? 'text' : 'password'}`.
- **Two non-conflicting reveal paths.** Mouse/touch is **hold-to-reveal** (Pointer Events:
  `pointerdown` shows — with `preventDefault()` so the button doesn't steal focus; the `click`
  browsers still synthesize after release is inert since no `onClick` is bound — and
  `pointerup`/`pointerleave`/`pointercancel` end the hold). Keyboard is a **sticky toggle**
  (Enter/Space flip visibility once per physical press — OS key auto-repeat is ignored;
  `preventDefault()` on Space stops page scroll), since press-and-hold isn't reachable by
  keyboard. The pointer re-mask handlers only act while a hold is in progress, so a plain
  hover-out can't cancel a keyboard-toggled reveal; blur always re-masks so a password is never
  left exposed.
- **Wired in without breaking label wiring:** Login uses `PasswordInput` directly; `FormField` now
  renders it whenever `type="password"`, so Signup (password + confirm) and ResetPassword (both
  fields) inherit the toggle. The `<label htmlFor>`/`id` association is preserved, so
  `getByLabelText('Password')` (unit) and `getByLabel('Password')` (staging e2e) still resolve to the
  field, never the button.
- **A11y/correctness:** button is `type="button"` (never submits), `aria-label` reflects the action
  ("Show password" / "Hide password"), the icon is `aria-hidden`, and `autoComplete`
  (`current-password` / `new-password`) is untouched.
- **Tests:** a dedicated `password-input.test.tsx` (starts masked; pointer hold reveals then
  re-masks on up/leave/cancel; `preventDefault` on pointer-down and on Space — repeats included;
  Enter/Space sticky toggle flips once per press with auto-repeat ignored; a sticky reveal
  survives hover-out; blur resets; does not submit its form; still accepts typed input) plus a new
  `form-field.test.tsx` pinning `FormField`'s branch wiring (`aria-invalid` +
  `aria-describedby`/accessible description forwarded through both branches, `type="email"`
  passthrough, empty error = no error) and page-level assertions on Login/Signup/ResetPassword.
  Full web gate green (eslint, prettier, tsc, vitest ≥80% coverage, vite build). The auto-repeat
  guard, hold-gated re-mask, and `FormField` pins came out of the pre-merge adversarial review
  (4 lenses + refute votes).

## 2026-07-08 — Bound the in-process rate limiter's key map (last non-owner hardening item)

Closes Track-1.1 in `planning/outstanding-work.md` (#141) — the third and final low/latent DoS item
from the #131 adversarial review (items 1 and 2 shipped as #138/#137).

- **`InProcessRateLimiter` now bounds its key map.** The per-hit reclaim only dropped a key's entry
  when that key was *re-hit*, so a flood of one-shot distinct keys — attacker-varied emails/IPs
  behind the public deletion-request limiters — accumulated one lingering entry apiece. A new
  `max_keys` ctor arg (default `MAX_KEYS = 100_000`) plus a `_sweep_expired(now)`, invoked from
  `hit()` once the map outgrows `max_keys`, reclaims every *fully-expired* key (newest timestamp
  already aged out of the window) in a single pass. A key with any live timestamp is left untouched,
  so **no live rate-limit window is ever weakened** — the per-user LLM cap (this class is shared with
  the cost guard) and the per-email / per-IP deletion caps are all unchanged. `max_keys` therefore
  bounds the *lingering fully-expired* keys; a flood that keeps its keys live inside the window is
  bounded instead by arrival-rate × window, by design.
- **Sweep hysteresis (post-review addition).** The O(n) sweep is throttled to at most once per
  window: a key still live at the last sweep cannot fully expire until a window later, so re-scanning
  sooner reclaims nothing — this stops a sustained live-key flood from turning the sweep into a
  per-request CPU sink on the request event loop, while holding the memory bound to the same order.
- **Whitebox tests** (`apps/api/tests/quota/test_ratelimit.py`) prove: only fully-expired keys are
  reclaimed; a *mixed*-window key (oldest timestamp expired, newest still live) survives the sweep
  and keeps counting against its limit; live keys are never evicted (the map may legitimately exceed
  `max_keys`); the sweep re-runs at most once per window; and the live size stays bounded across a
  many-window soak. Internal hardening only — no API, schema, or user-facing behaviour change.

## 2026-07-08 — Planning reorganization, round-3 close-out & `/next-task` tooling

A validated close-out and restructure of the planning surface, so what's left is unambiguous.
Every "done" claim below and in the planning docs was first **re-verified in-tree** (parallel
validation agents over the code, CI config, git/GitHub state, doc-link integrity, and a
repo-wide completeness sweep) before any file was changed.

- **Round-3 sweep closed out.** Items 1/3/2b/2a merged as #135–#138 (previous section). Item
  **2c** (bound the shared `InProcessRateLimiter`) is the **one remaining non-owner code item** —
  moved with its ready-to-implement spec to `planning/outstanding-work.md` **Track 1.1**
  (pause-for-review: the class is shared with the LLM cost guard). Item 4
  (`proficiency_cefr_band` metric) stays **skipped** — a categorical, process-local gauge only
  judgeable against the live CEFR panel, so it's deferred into the Phase-5 live wiring (Track 2
  (B)). `planning/doable-now-round3.md` deleted per its own final-PR instruction (mirroring
  round 2's removal in #128).
- **Planning reorganized into three tracks.** `outstanding-work.md` restructured by *who can act*:
  **Track 1** code-doable-now (item 2c + the open code issues #99/#80/#95 — newly surfaced on the
  board — + the optional post-v1 pull-forwards), **Track 2** owner-gated (prod cutover, Phase-5
  live observability, owner setup residuals), **Track 3** deferred-by-decision (mobile → store
  consoles → launch). `planning/README.md` rewritten as a start-here index.
- **Phase-8 task file synced to shipped reality.** #130–#133 had shipped the code slice but left
  0/36 boxes ticked; now 8.1.1, 8.2.1, 8.2.3, 8.2.4, 8.4.1, 8.7.1 are `[x]` with PR refs and
  8.1.2, 8.1.3, 8.2.2, 8.3.1, 8.3.2 are `[~]` (code half done; prod-URL/console half owner-gated,
  incl. 8.3.2's doc half which was already satisfied but uncredited). `task-tracker.md`'s Phase-8
  row corrected from "not started" to ◐ code-slice-done.
- **`/next-task` skill added** (`.claude/skills/next-task/`) — the single-item sibling of
  `/run-phase`: drives one Track-1 board item end-to-end via a fresh **Opus/max**
  `phase-task-runner` agent (implement → verify → PR → self-merge or pause), with the
  local-environment gotchas (offline-only local tests, `corepack pnpm`, repo-wide `mypy`, OpenAPI
  regen discipline) baked into the prompt. The orchestrating session stays on the session model;
  implementation agents run Opus.
- **Doc-link CI broadened.** `scripts/check_doc_links.py` now also scans `planning/**/*.md` +
  `infra/**/*.md`, so retiring a planning file can no longer silently strand
  links (previously only links *from* docs/README/CHANGELOG were protected).
- **Stale-doc fixes:** `phase-task-runner.md` / `run-phase` no longer point at the retired
  numbered design docs / phase-0 task file; `deploy-staging.yml`'s header no longer claims
  `DEPLOY_ENABLED` is unset (it's been `true` since 2026-06-29 — every `main` merge really
  deploys staging); `apps/web/README.md` dropped the long-deleted `placeholder-screen.tsx` entry;
  the root README planning pointer now starts at `planning/README.md`.

## 2026-07-07 — Round-3 doable-now sweep

A third post-close-out sweep of the non-owner/prod/mobile hardening items tracked in
[`planning/outstanding-work.md`](planning/outstanding-work.md), led by the accessibility
colour-contrast pass.

- **Accessibility — WCAG 2.1 AA colour-contrast pass (#135).** The advisory axe sweep added in #127
  flagged serious `color-contrast` violations on every authenticated surface (Dashboard / Generate /
  Review / Discover / Settings — 23 nodes: primary buttons, blue links/badges, and the red/green
  tinted rating pills + status chips). Fixed at the **design-token** layer in `src/index.css`, not
  per-component: `--primary` (and `--ring`) nudged from systemBlue `#007AFF` to a deeper, same-hue
  `#006CE0` so **white-on-primary** buttons and **`text-primary` links** clear 4.5:1 in light; the
  light `--hig-red-deep` / `--hig-green-deep` text hues deepened, and the dark `--hig-red-deep` /
  `--hig-blue-deep` text hues **lifted above their vivid fill** (the "re-pointing trick" now carries
  the AA-safe text hue, not merely the vivid), so the tinted pills/chips clear AA on the dark card in
  **both themes**. The blue chips (Languages / user-menu / dashboard badges / the `tinted` button)
  moved off `bg-primary/15` onto the unchanged vivid `bg-hig-blue/15` so the deeper button-primary
  can't mute them, and the daily-limit panel's body copy dropped its `/80` opacity. The Apple-HIG
  identity is intact (same hues, deeper lightness only). The `e2e/a11y.spec.ts` sweep now **asserts
  zero serious `color-contrast`** on the swept surfaces (the `e2e` job's `@a11y` run dropped its
  `|| echo` guard) and a new browserless `src/token-contrast.test.ts` re-derives contrast from the
  real `index.css` tokens to lock **both** themes (axe only sweeps light). Residual, documented: the
  iOS-brand **solid** buttons — white-on-systemBlue (dark primary) and white-on-systemRed
  (destructive confirm) — render only in dialogs / dark mode, never on the swept light happy path, so
  they stay as the tracked brand exceptions (floored at the 3:1 UI minimum by the token test).
- **Base-image digest refresh (#136).** Bumped the pinned `python:3.12-slim` digest in
  `apps/api/Dockerfile` from `sha256:6c4dd321…` to the current multi-arch index digest
  `sha256:423ed6ab…` (the tag had drifted, picking up base-OS updates). The builder and runtime
  stages stay in lockstep on the same pin; the `build` CI job (image build + `/health` smoke) is the
  gate. Closes the "base-image digest pin needs periodic refresh" tech-debt line.
- **Public deletion — per-IP throttle (#137).** `POST /account/deletion-request` had only a
  per-address cap, which a distinct-email flood from one source slips past (each email is a fresh
  key). Added a coarser **per-IP** cap (30/hour, checked first; client IP from the first
  `X-Forwarded-For` hop that Cloud Run sets, else the peer) reusing the same `InProcessRateLimiter`.
  Both caps return the same generic 429 so neither leaks which tripped. OpenAPI unchanged (the added
  `Request` + limiter dep aren't schema params). Closes the second of the three low/latent
  DoS-hardening items from the #131 review.
- **Public deletion — indexed `auth.users` lookup (#138).** `find_auth_user_id_by_email` (the email →
  auth-user resolution behind the public deletion-request form) paged the GoTrue Admin *list-users*
  API linearly. It now tries a single **indexed** `SELECT id FROM auth.users WHERE lower(email) = …`
  on the privileged (RLS-bypassing owner) session first — removing that unauthenticated-endpoint →
  Admin-API fan-out — and **falls back to the Admin API** on any `SQLAlchemyError` (e.g. a deployment
  whose owner role lacks `SELECT` on `auth.users`), so it can only speed the flow up, never regress
  it. Offline unit tests cover both the DB fast-path and the denied→admin fallback (mock session);
  the existing live-stack integration test exercises the real query. Closes the first of the three
  #131-review DoS items. OpenAPI unchanged.

## 2026-07-06 — Phase 8 compliance & store (buildable code slice)

Pulling the **CI-verifiable** half of Phase 8 (compliance & store readiness) forward, ahead of the
owner-run store/prod work (App Store Connect / Play Console entry, device screenshots, publishing).
Mobile/Capacitor, prod cutover, secrets, and migrations are untouched.

- **Privacy policy (#130, 8.1.1).** Replaced the Phase-0 `docs/privacy-policy.md` stub with a
  complete **GDPR privacy policy**: data categories (account email, learning content, content sent
  for AI generation, opt-in analytics, error diagnostics, technical/local storage); **Supabase (EU)**
  as the primary store; **Google Gemini** as the production **LLM provider** (Groq dev-only); lawful
  bases (contract / consent / legitimate interest); international transfers (SCCs/adequacy) + a
  sub-processor table; retention; the full data-subject rights; and a dedicated **export / delete**
  section (in-app Account actions + the public `/delete-account` form). Controller "Lengua", contact
  `privacy@lengua.app`. Added `scripts/check_doc_links.py` (stdlib, no network) + a `docs` CI job that
  asserts every relative markdown link across `docs/**` + `README.md` + `CHANGELOG.md` resolves
  (67 links, 7 files) — the "link-check in CI" the task's verify calls for.
- **Public deletion form + legal routes (#131, 8.1.2 + 8.3.1).** The store-required public compliance
  surfaces. **API:** two intentionally-**public** endpoints behind the external deletion path Google
  Play requires — `POST /account/deletion-request` (rate-limited per email, a generic
  **non-enumerating** ack, emails a signed one-hour HMAC token) and `POST /account/deletion-confirm`
  (verifies the token, then runs the **same** two-step cascade as in-app `DELETE /account`: domain
  rows on the privileged session → the Supabase `auth.users` record). Ownership is proven by the
  emailed token, not a session, so both are exempted from the route-auth / no-guest guards (like
  `/feature-flags`). A **mailer seam** (`app/mailer.py`: `LoggingMailer` no-egress default,
  `ResendMailer` when `RESEND_API_KEY` is set) mirrors the LLM seam — no SMTP to build/test; real
  delivery activates at the owner's Resend setup (issue #103). **Web:** `/privacy` (the published GDPR
  policy), `/support`, and the public `/delete-account` form, all in a sign-in-free `StaticLayout`; a
  site footer (Privacy + Support) on every shell and Account-screen links to both. A 6-vector
  adversarial security review held (no unauthorized deletion / token forgery / body-enumeration; correct
  cascade); it also found and this PR **fixed** a latent mailer-transport-error enumeration oracle, and
  **logged** the residual low/latent DoS-amplification hardening in `outstanding-work.md`. OpenAPI +
  `api-types` regenerated.
- **Launch-blocker E2E assertions (#132, 8.2.1 + 8.2.3 + 8.2.4).** Tests only — no UI rebuilt.
  Declining analytics consent now provably loads **zero** analytics across a full authenticated
  session (not just `/login`); the in-app export download's contents are asserted **equal** to the
  `GET /account/export` response bundle (not just the filename); and in-app account deletion is
  asserted **reachable via in-app navigation only** (no external URL) and to **clear the session**.
  The gate-blocks-even-with-a-key invariant stays unit-covered in `src/lib/analytics.test.ts`, and the
  real delete cascade in the backend integration tests.
- **Store-listing & data-safety source of truth (#133, 8.4.1 + 8.7.1 + 8.2.2).** Added
  `docs/store-listing.md` as the single source both stores reference: the published URLs; the
  store-listing copy (name / subtitle / short + full description / keywords / category) capped at the
  **shorter** of the Apple/Play limits and validated in CI by `scripts/check_store_listing.py` (wired
  into the `docs` job) so one copy fits both; the **data-inventory matrix** the Apple App Privacy +
  Play Data Safety answers derive from (email / user content / analytics / crash diagnostics /
  identifiers × purpose / linked? / tracking?, tracking = No throughout); and per-processor **data
  residency**. Added a Data-residency (GDPR) record (EU regions) to `docs/runbook.md`, and updated the
  README (public deletion endpoints + public pages) + docs index. **This completes the buildable,
  CI-verifiable Phase-8 slice; everything remaining is the owner store/prod cutover.**

## 2026-07-06 — Round-2 doable-now sweep — PRs #126, #127, #128

A second post-close-out sweep clearing the last non-owner/prod/mobile items from
`planning/outstanding-work.md`: CI-only test debt, the advisory-a11y broadening, and code-comment
hygiene.

- **API tests (#126).** Landed the two account-lifecycle integration tests deferred from #123: an
  export-under-**real-RLS** test that drives `GET /account/export` through the un-overridden scoped
  `get_db` (authenticated role, Postgres RLS enforcing — not just the app-layer `WHERE user_id`
  filter) and proves A's export is scoped to A with none of B's rows; and a
  deleted-but-unexpired-token test proving a still-valid JWT for a just-deleted account reads a `200`
  **empty** bundle (never a leak or `500`) inside the stateless-JWKS `exp` window. Both are
  `@pytest.mark.integration` (live Postgres + Supabase auth), so they execute in CI's backend job.
- **a11y CI (#127).** Broadened the advisory accessibility pass beyond the static `/login` page: a
  new `@axe-core/playwright` sweep (`apps/web/e2e/a11y.spec.ts`) logs in as the seeded demo user under
  the FakeLLM e2e harness and runs axe on Dashboard / Generate / Review / Discover / Settings, logging
  + attaching violations without ever asserting. Wired into the `e2e` job as an advisory run (the
  required run `--grep-invert`s the `@a11y` tag; the advisory run is `|| echo`-guarded), so it is
  never a merge gate. Its first run surfaced serious `color-contrast` violations on every
  authenticated surface — tracked under the post-v1 accessibility-pass backlog. *(Superseded in
  part by #135: the sweep now **asserts** zero serious/critical `color-contrast` — that one rule
  became a merge gate; all other axe rules remain advisory.)*
- **Docs (#128).** Repointed the code-comment citations of the planning design docs deleted in
  #115/#116 (`app/quota.py` ×3, `app/repositories/__init__.py`, `lengua_core/llm/keys.py`,
  `.github/workflows/ci.yml`, `apps/web/e2e-staging/signup.spec.ts`) to the root `CHANGELOG.md` /
  self-documenting text. The applied migration `0006`'s comment is left as-is (migrations are
  off-limits even for comments). Comment-only, no behavior change.

---

## 2026-07-05 — Post-close-out hardening, perf & polish — PRs #117, #119, #121, #122

A run of agent-implemented, CI-verified PRs landed right after the planning close-out — hardening the
API boot path and the web tap-a-word / accessibility surface, then trimming the web bundle and paying
down UI-polish + test-coverage debt.

- **API (#117).** A **boot-time config guard** logs `CRITICAL` when `env ∈ {staging, prod}` and
  `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_URL` is unset, so a misconfigured `DELETE /account`
  surfaces loudly at startup instead of failing only on the first deletion (a strict no-op for
  `local`/`ci`/`test`/`e2e`, which run without the key by design). The dark `GET /experimental/*`
  route is now **hidden from the public OpenAPI** (`include_in_schema=False`) — kept out of
  `openapi.json` and the generated `api-types` client while it ships dark, with the runtime
  404-until-flag behavior unchanged. The coverage gate is **DB-reachability-aware**: a no-DB local
  `pytest` skips the integration tests and relaxes `--cov-fail-under` (loud banner) instead of a
  false red, while CI (Postgres up) still enforces ≥80%. And the in-process rate-limiter reclaims a
  user's window entry once it empties, so its map stays **bounded** (mirroring the size-capped
  discover cache).
- **Web (#119).** Fixed a **tap-a-word bug** — the explain-word query cached by `(languageId, word)`,
  so a word recurring across cards showed the first card's explanation; the query key now includes
  the sentence/card, giving each card its own note. Accessibility: `LanguageText` / `TappableSentence`
  now emit `lang={language.code}` (WCAG 3.1.2) so screen readers pronounce foreign text correctly;
  the tap-a-word popover manages focus (move-in / restore-to-trigger); and the Languages row plus the
  dashboard tiles/quick-actions gained the app focus-visible ring.
- **Web perf (#121).** Route-level code splitting — the authenticated non-landing screens are
  `React.lazy` chunks fetched on first navigation (auth screens + Dashboard stay eager), with the
  `Suspense` skeleton around the app-shell `<Outlet />` so the nav stays mounted. Sentry now loads via
  dynamic `import()` only when a DSN is set (out of the initial bundle), stable vendor chunks
  (react + router / react-query / supabase) are split out, and the stock Vite favicon is replaced by a
  real one.
- **Web polish & test coverage (#122).** An Apple-HIG className pass on the surfaces the redesign had
  missed — the tap-a-word popover moves to the design system (`rounded-lg` / `shadow-raised`, dotted-
  underline word affordances), a `text-body` / `text-subhead` / `text-footnote` type-scale sweep across
  the auth + dialog + helper text, the Generate save bar on the shared `.frosted` utility, and
  right-aligned vowel-marks toggles. Plus coverage debt: `lengua_core.prompts` enters the gate with a
  (vowelized × level) / (known-words × topic) branch matrix, and `use-toast.ts` is carved out of the
  web `ui/` coverage exclusion with a reducer + store test.

---

## 2026-07-05 — Planning close-out (staging-leg validation) — PRs #115–#116

Validated every **as-code** and **staging-live** acceptance criterion that could be checked now
(read-only against live staging + local/CI test runs), and ticked it with evidence. **No prod
mutation, no deploy, no migration.** 17 boxes flipped to done:

- **Phase 0 — `0.7.7`**: CI secrets `GCP_REGION` + `SENTRY_ORG` present (`gh secret list`; the armed
  staging CD consumes them green).
- **Phase 2 exit gate** (as-code): no hard-coded user + route-auth 401s; app-layer **and** RLS
  cross-tenant isolation; JWT rejection (expired / forged / `alg:none`); profiles-on-first-login +
  demo-seed full loop; account cascade-delete with no orphans + auth-user removal; legacy SQLite
  import. Two DB-free suites ran locally (27 passed); the seven DB-backed suites are green in CI run
  **28715034639** (live Supabase Postgres+Auth, ≥80% branch coverage enforced).
- **Phase 6 staging leg**: Artifact Registry EU repo with SHA + `:staging` tags (`6.1.3`);
  `lengua-api-staging` Cloud Run service `Ready`, `/health` 200, 11+ retained revisions (`6.1.4`,
  `6.8.1`); Alembic history applied to the staging DB at head (`6.2.2`); the merge→staging CD steps
  (build-push, deploy, deploy-web, smoke) all green on the latest `main` deploy — run 28715034653
  (`6.6.1`, `6.6.2`, `6.6.4`, `6.6.5`); the *"merging to `main` ships staging automatically with an
  applied migration"* exit gate; and *"no secret leaks to the client + security scans pass"* (fresh
  `pnpm` build → bundle carries only the Supabase **anon** key + public URLs; gitleaks / pip-audit /
  pnpm-audit all green in CI).

Left **unticked** (unchanged): everything prod-gated (`6.1.5`, `6.2.3`, `6.7.x`, prod promotion /
rollback proof), owner dashboard/cred (all of Phase 5 live observability — Grafana/Sentry/PostHog/
uptime), owner account setup (Google/Apple OAuth, Resend SMTP + SPF/DKIM, Vercel project link,
branch protection, Dependabot), and the two remaining exit-gate clauses that need those.

Docs pruned in the same pass: deleted the resolved point-in-time staging-validation material
(`planning/staging-validation.md` + `planning/staging-validation/**` + `planning/staging-fix-handoff.md`),
slimmed the numbered design docs to implemented-status stubs, and made this changelog + `outstanding-work.md`
the single source of truth for done-vs-left.

---

## Live-staging validation & hardening (2026-06-30 → 2026-07-05) — PRs #79–#98, #100–#104

After staging went live and CD was armed (`DEPLOY_ENABLED=true`, 2026-06-29), a 50-agent live-staging
validation exercised the deployed stack (web + API + DB) as the demo user and surfaced 25
correctness/UX/hardening items; a multi-agent fix pass then landed all of them. **All 22 findings
(S1–S22) are fixed or accepted**, and the full study flow (login → generate → save → review incl.
Hebrew RTL → discover → settings → account) is verified working on live staging with no errors.

- **S1 (right-to-erasure, #91)** — guarded Alembic `0006` adds `profiles.id → auth.users(id) ON
  DELETE CASCADE` (+ orphan purge) so account deletion actually erases all user data; owner-approved,
  applied to the staging DB (`profiles_id_fkey` validated).
- **S16/S17 (#83)** — CORS `Access-Control-Expose-Headers: Retry-After`, API security-headers
  middleware (nosniff / `X-Frame-Options: DENY` / Referrer-Policy / HSTS), and a baseline CSP on the
  web tier; owner-approved.
- **S2** OAuth Google-only default · **S3/S12/S14 (#88)** language add/CEFR atomicity · **S4 (#79)**
  idempotent staging seed (demo deck = 6 ES + 6 HE/RTL card pairs from 3+3 seeded sentences) · **S5 (#82)** Sentry per-env tag + sample
  rate · **S6/S13/S19 (#86)** review order + RTL copy · **S7/S11 (#89)** used-word coverage +
  empty-generate guard · **S8/S15 (#84)** + **S22 (#97)** discover cache / known-word / vowel-mark
  dedup · **S9/S10 (#90)** settings server-side validation. **S21** diagnosed benign (Cloud Run 4xx
  platform logs). **S18** stable Vercel staging alias resolved (#71). **S20** (prod `/docs`) accepted,
  to gate before public launch.
- **Sign-up fix (#100–#104)** — live-staging register → logout → login made green by disabling email
  confirmation on staging (interim `mailer_autoconfirm=true`); the `{}`/`[object Object]` auth alert
  fixed (#102). **Prod follow-up (issue #103, owner):** real Resend SMTP on a verified domain, then
  re-enable email confirmation — must NOT ship prod with autoconfirm on.

Two reusable validators are kept in the repo (out of CI, they hit live staging):
`apps/api/scripts/staging_smoke.py` (13/0/0) and `apps/web/e2e-staging/*.spec.ts` (6/6).

---

## M3 — React web app at full parity (Phase 4) — PRs #38–#50

Delivered the full React + TypeScript (Vite) web app, closed by an end-to-end full-loop Playwright
spec:

- App shell & foundations (theming, routing, TanStack Query, Supabase client); a typed, authed API
  client generated from the OpenAPI contract.
- Auth screens with session handling; language/CEFR management.
- **Generate**, **Review** (FSRS loop, reveal + 4-button grade, tap-a-word, keyboard shortcuts),
  **Discover**, and **Settings/Account** screens.
- RTL / diacritics / complex-script rendering; cross-cutting UX + consent states; a per-user daily
  review-limit fix.
- A later Apple-HIG redesign sweep (PRs #105–#114) refreshed foundations, app shell/nav, the review
  experience, the Dashboard home screen, forms, and auth cards.

## M2 — Multi-user with the LLM cost guard armed (Phases 2 & 3)

**Phase 2 — Auth & multi-tenancy (PRs #24–#30).** Supabase JWT verification → typed `current_user`
(HS256 secret or RS256/ES256 via JWKS; `exp`/`aud` checked; expired/forged/`alg:none` rejected) with
`GET /me` and a strict CORS allowlist; per-user scoping of every query; a `profiles`-on-first-login
trigger (`plan='free'`) with no-guest enforcement; Supabase Auth config (email confirmation, password
policy, redirect allow-list, branded email templates); Postgres **Row-Level Security** with a
per-request `authenticated` DB identity (defense-in-depth beneath app-layer scoping); a one-off
legacy SQLite→Postgres history import; and account-lifecycle endpoints (`GET /account/export` +
hard `DELETE /account`).

**Phase 3 — LLM cost guard (PRs #31–#37).** Usage accounting with a server-only kill-switch privilege
model; per-user daily caps; rate limiting + an email-verified gate + a signup-abuse guard; a global
daily-budget kill-switch; a concurrency cap with backoff and a BYOK key-resolution seam;
request/token cost minimization with Discover reuse; and cost-guard observability (spans + metrics) —
proven by a **zero-paid-usage load test**.

## M1 — Backend core loop over HTTP (Phase 1) — PRs #15–#23

Ported the domain logic into a pure `lengua_core` package; put Groq/Gemini/Fake behind one
`LLM_PROVIDER` seam; built the async SQLAlchemy persistence foundation (repository → service layers);
added Alembic + the first full-schema migration and dev-user seed; exposed the complete core-loop
HTTP surface (generate / save / review / discover / explain / proficiency / settings); and added the
OpenAPI contract dump + drift test, `api-types` codegen, and the OpenTelemetry / structured-log
skeleton.

## Phase 0 — Foundations — PRs #1–#14

Stood up the monorepo (`apps/api` + `apps/web`), relocated the domain package and the legacy
Streamlit app under `apps/api` (kept runnable for reference), scaffolded the FastAPI + React/Vite
shells, shared test infra (factories, FakeLLM, test Postgres, E2E seed), the per-PR CI quality gate
(lint/types · backend + frontend tests at ≥80% coverage · build · E2E with the LLM stubbed ·
gitleaks/audit), and the autonomous build orchestration (`/run-phase` skill + `phase-task-runner`
agent). *Owner-deferred to launch: branch protection (`0.6.3`), Dependabot (`0.6.4`).*

## Phase 5 — Observability (as-code) — PRs #51–#59

The observability layer, complete **as-code** (CI-verified); the **live** half (traces/logs/metrics
rendering in Grafana, Sentry alert routing, PostHog insights, external uptime) is owner-deferred
until the dashboards/creds are wired ([go-live §G](planning/go-live-activation.md)):

- OpenTelemetry foundation; custom spans (`llm.call` / `quota.check` / `review.grade`) and
  provider-agnostic domain metrics.
- Structured, correlated logging (OTLP log export carrying `trace_id`/`span_id`/`user_id`); W3C
  `traceparent` propagation for client → API → DB / LLM trace continuity.
- Sentry error tracking (API + web, dual DSN); Grafana dashboards-as-code (RED / cost-guard /
  product / infra skeleton) with a drift test; consent-gated, PII-free PostHog product analytics.
- Alerts-as-code (5xx > 5% / 5m, p95 > 1.5s / 10m, LLM budget < 20%, uptime) + an external
  uptime-monitor descriptor and runbook health-check entries.

## Phase 6 — Infra, environments & CI/CD (M4 staging leg) — PRs #60–#78

Infra + CD **as-code**, then armed and green-verified end-to-end on the staging leg:

- `/ready` readiness probe + a digest-pinned, non-root API `Dockerfile` (CI build-run smoke).
- Per-env CORS with a no-wildcard guard; a web-bundle secret-leak audit (CI grep + a source-scan
  unit test).
- Feature flags: env default overlaid by a global `feature_flags` table, cached with a TTL so a
  toggle takes effect **with no redeploy**; a public `GET /feature-flags`; the `word_of_the_day`
  surface ships dark.
- The gated staging + prod CD pipeline (`deploy-staging.yml` / `deploy-prod.yml`) with an
  `alembic -x env=…` resolver, discrete logged migration jobs, digest-promotion to prod behind a
  `production`-environment approval, shared composite deploy/smoke actions, and a one-click
  `infra/deploy/rollback.sh`.
- The go-live runbook. CD was then armed (`DEPLOY_ENABLED=true`) and the staging leg brought green:
  JWKS env fix, SPA rewrite, stable-alias CORS smoke, the Supabase session-pooler DB-URL fix
  (IPv6→IPv4), and env-var `#`-comment handling. **The prod leg (gated promotion) remains an
  owner cutover.**

---

## Locked decisions & rationale (preserved)

Design rationale worth keeping — the numbered `planning/0X-*.md` design docs were deleted after
completion (PR #116; git history retains them):

- **Stay-free-by-design.** Every dependency (LLM, DB, hosting, observability) is chosen to fit a
  viable free tier — the reason the whole cost-guard + provider-choice architecture exists.
- **LLM provider.** Pluggable behind one interface, picked by `LLM_PROVIDER`: **Groq** free tier for
  all dev/CI, **Fake** for E2E (zero real calls), and **Gemini** as the intended prod/launch default
  reachable by a single env-var flip **with no code change**. **BYOK was rejected for v1** in favor
  of an operator-funded, capped key (the reason a cost guard is needed at all); BYOK remains the
  growth escape hatch.
- **Ship all platforms together.** The web app is built first *because Capacitor wraps it*, but the
  launch gate requires web + iOS + Android ready simultaneously.
- **v1 scope.** Keep all current features (Generate, Review, Discover, Settings, multi-language,
  vowel marks, tap-a-word, Anki import). `profiles.plan` is a deliberate **paid-ready seam with zero
  payment code in v1**. **Local** review reminders are in v1; **server** push is out. Offline is
  online-first at launch, with a fast-follow that caches the due batch and **queues review grades
  offline** (TanStack Query persistence + background flush; generation stays online-only) — the
  stated reason TanStack Query was chosen. TTS is post-v1, on-device/browser first.
- **Backend host = Cloud Run**, chosen over Render/Fly: Render's free web services sleep ~15 min with
  a slow wake (bad for a mobile app's first request of the day); Cloud Run scales to zero but wakes
  fast with a large free request allowance. **Fly.io is the fallback.**
- **SLOs.** API availability target **99.5% monthly** (cold starts count); a p95 latency SLO on
  non-LLM routes; **measure but do NOT SLO** the LLM/provider latency (provider latency dominates);
  define an error budget + burn-rate alerts once there is real traffic.
- **Architecture invariants.** Routers → services → repositories → DB, with repositories the only
  layer that touches the DB; the LLM provider seam is a config flip, never a code change, and
  fails fast at boot on a missing key.
- **Compliance is a launch blocker** (in-app account deletion + published privacy policy + store
  data-safety forms), not a nice-to-have. **EU** Supabase region; full GDPR posture (consent +
  export + delete); PostHog anonymized + consent-gated from v1.

## Not yet done (see `planning/outstanding-work.md` + `planning/go-live-activation.md`)

**M4 prod cutover** (owner — go-live §F: prod DB schema + IPv6→session-pooler swap, prod Auth/CORS,
`production`-environment reviewer + digest promotion, web prod, rollback drill) · **Phase 5 live
observability** (owner — Grafana/Sentry/PostHog/uptime dashboards + alert channels) · **Phase 7**
mobile (Capacitor, store accounts, on-device validation) · **Phase 8 store-console half** (Apple
privacy labels, Play Data Safety, age ratings, console listings, screenshots, closed tests — the
buildable code slice shipped 2026-07-06, see above) · **Phase 9** launch. Plus owner setup: Google/
Apple OAuth, Resend SMTP + SPF/DKIM/DMARC (+ re-enable prod email confirmation, issue #103), branch
protection, Dependabot, prod `/docs` gating.
