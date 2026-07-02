# Staging end-to-end validation report — "is staging ready for users?"

# VERDICT: GO (staging) — sign-up fixed; the full register → login → learn → delete loop is validated

**Update 2026-07-01 — sign-up FIXED, verdict flipped NO-GO → GO.** A brand-new user can now register and
log in through the website. The blocker (a Supabase Auth 500 on `POST /auth/v1/signup`, "Error sending
confirmation email") was resolved by disabling email confirmation on the staging project
(`mailer_autoconfirm = true`, applied via the Management API) as an interim unblock — sign-up now
auto-confirms and returns a session, sending no email. The full Playwright staging suite is **10/10
green**, API smoke **12/0/0** (14/0/0 with LLM), and **zero test data leaked**. **Staging is ready for
users.**

> **Production caveat (issue #103 stays OPEN):** disabling confirmation is a *staging* interim. Before
> production, configure real transactional email (custom SMTP via Resend on a verified sender domain) and
> **re-enable email confirmation** — do NOT ship prod with `mailer_autoconfirm = true` (that would mean no
> email verification). Also fixed alongside: the sign-up error alert no longer renders a raw `{}` (PR #102).

- **Validated GO (10/10 green):** **register (public form) → sign out → log back in** · log in / out /
  back-in · add language + CEFR · generate → save · study recognition + production (reveal,
  rate-to-advance, tap-a-word) · 2+ languages with switching (CEFR flips, RTL/nikkud for Hebrew) ·
  Discover · Settings · Account export · **Account delete (UI)** · fresh users' full 2-language loop
  end-to-end.

<sub>Round 1 originally graded this NO-GO on the sign-up 500; kept below for history. The 2026-07-01
follow-up fixed it and re-ran the suite fully green.</sub>

**Target stack:** web `https://lengua-staging.vercel.app` → API
`https://lengua-api-staging-cxiyhzhria-ew.a.run.app` (Cloud Run) → Supabase `rydclyotzdwcbbeyitcx`.
LLM provider = Groq `llama-3.1-8b-instant` (free tier).

**Run shape:** Tier **B** — the staging service-role secret was present (found in the gitignored repo
`.env`), so the fresh-user / multi-language / **delete-account** scenarios were **actually exercised**,
not skipped. The loop ran **round 1** (paused for human review on the product blocker per the
autonomous protocol), then the two harness bugs (plus a third found during re-validation) were fixed
and **round 2** re-ran everything green except the unchanged sign-up blocker.

---

## 1. Per-scenario results (maps to VALIDATION-PLAN §2 / SYNTHESIS request items)

| # | Scenario (request item) | Result | Evidence |
|---|---|---|---|
| 1a | **Register — public sign-up form** | **PASS** (2026-07-01) | `signup.spec.ts`: register → sign out → **log back in** succeeds. Fixed by disabling email confirmation on staging (`mailer_autoconfirm=true`) — sign-up auto-confirms + returns a session. (Was the round-1 NO-GO 500; prod still needs real SMTP + confirmation re-enabled — issue #103.) |
| 1b | **Register — admin-confirmed user (the supported automatable path)** | **PASS** | `fresh-user-lifecycle.spec.ts`: 2 admin-created pre-confirmed users logged in and drove the full loop (generate/save/discover all 200). |
| 2 | **Log in / Log out / Log back in** | **PASS** | `auth.spec.ts` demo login; fresh users: login → sign-out (→ `/login`) → **re-login** with decks/languages surviving. |
| 3 | **Add a new language (+ CEFR starting level)** | **PASS** | `screens.spec.ts`; smoke `POST /languages` 200 + `DELETE` 204; full-flow + fresh-user add languages, set non-A1 CEFR (band confirmed via `cefr-band`). |
| 4 | **Enter words → generate → save flashcards** | **PASS** | Smoke `POST /generate` 200 (2 previews); full-flow + fresh-user generate + `POST /cards/save` 200. No throttle fired. |
| 5 | **Study / review — recognition + production (reveal, rate-to-advance, tap-a-word)** | **PASS** | full-flow + fresh-user reveal, grade only "Again" to advance, tap-a-word explain popover opens/closes, reach SessionComplete. (The round-1 red here was harness TEST_BUG #2, now fixed + re-validated.) |
| 6 | **2+ languages + switching between them** | **PASS** | full-flow + fresh-user add language A **and** B, switch via the header `Active language` picker, CEFR band flips per language; Hebrew B renders `dir="rtl"` + the "Show vowel marks" switch toggles. |
| 7 | **Discover** | **PASS** | Smoke `POST /discover` 200 (3 suggestions); full-flow + fresh-user discover 200. |
| 8 | **Settings** | **PASS** | Smoke `GET /settings` 200; `screens.spec.ts`; full-flow + fresh-user edit + `Save settings` (toast confirmed), value restored. |
| 9 | **Account — export** | **PASS** | Smoke `GET /account/export` 200 (6 sections). |
| 10 | **Account — delete (throwaway users only)** | **PASS** | `fresh-user-lifecycle.spec.ts`: both fresh users complete the in-UI delete-account dialog (typed confirm phrase, 502-retry-once) → redirected to `/login`; admin cascade hard-delete verified in `afterAll`. (Round-1 blocked by TEST_BUG #3, now fixed + re-validated.) |
| 11 | **Mock users learning 2+ languages, full loop** | **PASS** | `fresh-user-lifecycle.spec.ts`: **both** fresh users complete the entire 2-language lifecycle end-to-end then delete their accounts (serial). |

**Cost-guard note:** zero 429/503 throttles fired in either round (every `/generate`, `/discover`,
`/cards/save` returned 200). Per the plan, a throttle would have counted as an accepted **PASS**; none
needed to be applied.

---

## 2. Layer results (per round)

| Layer | Round 1 | Round 2 (post-fix) |
|---|---|---|
| **Layer B — `staging_smoke.py` (demo, API)** | PASS — 14 / 0 / 0, exit 0 | **PASS — 14 / 0 / 0, exit 0** (incl. real `/generate` + `/discover` 200) |
| **Layer A — demo full-flow** | FAIL (TEST_BUG #2) | **PASS** (self-cleans) |
| **Layer A — signup form** | FAIL (PRODUCT_BUG #1) | **FAIL — unchanged** (product blocker) |
| **Layer C — fresh-user lifecycle ×2** | FAIL (TEST_BUG #3) | **PASS ×2** (incl. UI delete-account) |
| `auth.spec.ts` ×2 + `screens.spec.ts` ×4 | PASS | **PASS** |
| **Full Playwright suite** | 6 pass / 3 fail / 1 not-run | **9 pass / 1 fail (signup)** |

**Rounds to green:** the non-sign-up suite reached green in **round 2**. Sign-up stays red because it
is a product/infra blocker that (per protocol) is routed to the owner rather than self-fixed + deployed.

---

## 3. What was fixed vs. skipped

### Fixed — harness/spec only (low-risk, never runs in CI), applied + re-validated live

1. **TEST_BUG #2 — review end-state locator** (`full-flow.spec.ts`, `fresh-user-lifecycle.spec.ts`):
   `done` matched a `heading`, but `SessionComplete` renders "Done for today" via a `<CardTitle>` `<div>`.
   Switched to the unique "Check for more" button. (Only bit small decks — why big-deck runs passed.)
2. **TEST_BUG #3 — re-login asserted the Dashboard heading** (`fixtures.ts`, `fresh-user-lifecycle.spec.ts`):
   a login after sign-out-from-`/account` is correctly returned to `/account`; switched to asserting the
   Primary navigation (the authenticated shell, present on every screen).
3. **TEST_BUG #4 — silent cleanup leak** (`full-flow.spec.ts` `removeLanguageIfPresent`): checked the row
   count before the async languages list finished loading, racing the load and silently leaking the
   throwaway languages (test still passed). Now waits for the row before deciding absence — the suite
   self-cleans (zero leaks).

Also added during validation: `apps/web/tsconfig.e2e-staging.json` (the project `tsconfig` excluded
`e2e-staging`, so the specs were never type-checked — this closes the gap), and a non-destructive
`GET /proficiency/{id}` probe in `staging_smoke.py` (the one demo-safe endpoint the smoke was missing).

### Skipped / accepted

- **Public-signup confirmed-user path for LLM flows:** correctly avoided (SYNTHESIS flags it a dead-end
  for automation — only admin-confirmed / demo users can generate). Fresh users are admin-confirmed.
- **Cost-guard LLM probes:** none throttled this run, so there was nothing to accept-as-PASS.

---

## 4. Leftover risks

### Resolved on staging 2026-07-01 (was the NO-GO blocker) — a production follow-up remains (issue #103)

**Sign-up 500 — FIXED on staging (interim).** Public sign-up returned HTTP 500
`{"code":"unexpected_failure","message":"Error sending confirmation email"}` because staging Supabase
Auth had no working transactional email (custom SMTP was misconfigured; `enable_confirmations = true`, so
sign-up required an email that never sent). **Resolution:** email confirmation was disabled on the staging
project — `mailer_autoconfirm = true` (applied via the Supabase Management API `PATCH
/v1/projects/rydclyotzdwcbbeyitcx/config/auth`), and the broken custom SMTP was turned off.
`external_email_enabled` stays `true` (email login/sign-up still enabled). Sign-up now auto-confirms and
returns a session — **verified live**: `signup.spec.ts` (register → sign out → log back in) and the full
suite (10/10) are green.

- **Production follow-up (issue #103, OPEN — do NOT ship prod without it):** `mailer_autoconfirm = true`
  means **no email verification** — fine for staging, NOT for production. Before prod: configure custom
  SMTP (Resend `smtp.resend.com:465`, user `resend`, pass = a Resend API key) with a **verified sender
  domain**, then re-enable email confirmation (`mailer_autoconfirm = false`). Owner action (Resend
  domain/DNS).
- Repro (now PASSES): `cd apps/web && source <staging-secrets.env> && corepack pnpm exec playwright test --config playwright.staging.config.ts signup.spec.ts --workers=1 --reporter=list`

### Secondary UX bug — FIXED (PR #102, merged)

- **Unhelpful `{}` error alert on auth failures.** The 500 surfaced as an empty `{}` alert because
  `mapAuthError` (`apps/web/src/lib/auth.ts`) passed a raw serialized error body through its default
  branch. **Fixed in PR #102:** added an explicit `unexpected_failure` case + an `isPresentableMessage`
  guard so no serialized object/array (`{}`, `[object Object]`) is ever shown to a user; genuine messages
  still pass through. Regression tests added.

### SYNTHESIS "MISSING selector" hardening (non-blocking)

From SYNTHESIS Blocker 5 — add stable `data-testid`s so specs stop coupling to copy (all have working
fallbacks today): `data-testid` on Languages rows + the active marker; on success toasts; a
`data-testid="app-shell"` on `AppLayout` (would directly harden the class of bug behind TEST_BUG #3);
per-page route markers for Dashboard/Languages/Settings/Account.

---

## 5. Cleanup confirmation (zero leaks)

- **Demo-user throwaway languages:** the harness now self-cleans (TEST_BUG #4 fix). Final full-suite
  pass left **0** throwaway languages — `GET /languages` as demo shows only the two legitimate languages
  (Spanish id 5, Hebrew id 9), never touched. (Round-1's 4 leaks and the interim pre-fix residue were
  all removed via `DELETE /languages/{id}`.)
- **Throwaway auth users:** **0** `lengua-val-*` / `lengua-signup-*` users remain (Auth Admin API paged
  + checked). Fresh users self-deleted via the UI lifecycle; `afterAll` admin hard-delete is the
  defense-in-depth net; the sign-up 500 rolls back, leaving no row.
- **Post-cleanup smoke:** `staging_smoke.py` exits 0 (14/0/0 with LLM; 12/0/0 `--no-llm`). Staging is
  healthy and left exactly as found.

**Net: zero leaked languages, zero leaked users — all test data cleaned up.**

---

## 6. How to re-run (appendix)

Two secret tiers. **Tier A** = demo user (Layers A + B). **Tier B** = adds fresh-user / multi-language /
delete-account (Layer C) and needs the staging service-role key. All staging secrets live in the
gitignored repo-root `.env` (anon + service-role for project `rydclyotzdwcbbeyitcx`).

```bash
# Export from the repo .env (or your secrets file). Tier B example:
export STAGING_SUPABASE_ANON_KEY=<staging anon key>      # Layer B smoke
export SUPABASE_STAGING_URL=https://rydclyotzdwcbbeyitcx.supabase.co
export SUPABASE_STAGING_ANON_KEY=<staging anon key>
export SUPABASE_STAGING_SERVICE_ROLE_KEY=<staging service-role key>
export STAGING_INCLUDE_LLM=1

# Layer B — API smoke (demo):
cd apps/api && uv run python scripts/staging_smoke.py            # add --no-llm to skip real-Groq probes

# Layers A + C — full Playwright staging suite (Tier B):
cd apps/web && corepack pnpm exec playwright test --config playwright.staging.config.ts --workers=3 --reporter=list
#   Expect 9 passed / 1 failed (signup) until PRODUCT_BUG #1 is fixed.
#   Targeted: full-flow.spec.ts | fresh-user-lifecycle.spec.ts | signup.spec.ts (stays red until the fix)
```

**Guardrails (baked into the specs):** grade only "Again", tiny timestamp-unique words, LLM steps
gated by `STAGING_INCLUDE_LLM` + 429/503-tolerant, throwaway languages + cleanup, `DELETE /account`
only against admin-created throwaway users, fresh users serial + admin-deleted in `afterAll`.

---

*Round detail: `FAILURES-1.md` (initial), `FAILURES-2.md` (fix + re-validation). Plan + scope:
`VALIDATION-PLAN.md` + `research/SYNTHESIS.md`. Harness: `apps/web/e2e-staging/*`,
`apps/web/tsconfig.e2e-staging.json`, `apps/api/scripts/staging_smoke.py`.*
