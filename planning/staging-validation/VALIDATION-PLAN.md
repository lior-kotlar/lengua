# Staging end-to-end validation plan — "is staging ready for users?"

**Target:** the live staging stack — web `https://lengua-staging.vercel.app` → API
`https://lengua-api-staging-cxiyhzhria-ew.a.run.app` (Cloud Run) → Supabase `rydclyotzdwcbbeyitcx`.
**LLM on staging:** Groq `llama-3.1-8b-instant` (free tier → ~$0 dollar cost, but cost-guard-limited).

This plan is the **discovery output (step 1)**. The deep, file-verified research it is built on lives in
[`research/SYNTHESIS.md`](research/SYNTHESIS.md) (read it first) and the six per-area notes in
[`research/`](research). The runnable instructions + prompts are in [`RUN.md`](RUN.md).

---

## 1. Goal & exit criteria

Prove a real user can complete the **entire** learning loop on staging, for **2+ languages**, including
account lifecycle — and that the logic behaves correctly, not just that pages render.

**Exit = GREEN** when, against live staging:
- Every scenario in §4 passes (or is explicitly, correctly SKIPPED with a stated reason — e.g. a
  cost-guard 429 on an LLM probe is a PASS, not a failure).
- The web Playwright staging suite (`apps/web/e2e-staging`) is green.
- The API smoke (`apps/api/scripts/staging_smoke.py`) exits 0.
- The fresh-user / multi-language / account-lifecycle driver (§3 Layer C) is green **or** cleanly
  skipped because the service-role secret was not provided (Tier A run — see RUN.md).
- All test users and test data created during the run are cleaned up (no leaked `auth.users`, decks,
  or throwaway languages left on staging).

---

## 2. What we are validating (maps to the request)

| Request | Where it's covered |
|---|---|
| Register | Layer A signup-form UI (form + "check your email") **and** Layer C fresh-user provisioning (admin-create a confirmed user = the only automatable "register → usable account" path) |
| Log in / Log out / Log back in | Layer A + Layer C (session persists; decks survive a logout/login) |
| Add a new language (+ CEFR starting level) | Layer A/C step "Add language A", "Add language B" |
| Enter words → generate → save flashcards | Layer A/C generate→save (LLM-gated, demo user) |
| Study / review (recognition + production) | Layer A/C review: reveal, rate to advance, tap-a-word explain |
| "Continue" / next card | review reveal + rate-to-advance (`data-rating`) |
| "Back" | **forward-only review** — modeled as nav-away/return or session restart, NOT prior-card (see SYNTHESIS Blocker 4 step 12) |
| 2+ languages, switching between them | Layer C multi-language pivot via header `Active language` picker; CEFR band flips per language |
| Discover | Layer A/C discover → "Use these words" → generate |
| Settings | Layer A/C settings save (daily new/total, discover count) |
| Account (export, delete) | Layer A export (demo) + Layer C delete-account (throwaway users only) |
| Mock users learning 2+ languages, full process | Layer C: ≥2 admin-created confirmed users, each does the full 2-language loop, then deleted |

---

## 3. Test layers (all against live staging)

**Layer A — UI happy path (Playwright, `apps/web/e2e-staging/`), demo user.**
The §4 flow driven through the real browser as the seeded `demo@lengua.test`. Bulk is structure /
read-only (zero LLM, fully parallel). The few LLM-touching steps (generate / save / review-grade /
discover / explain) are gated behind `STAGING_INCLUDE_LLM=1`, throttled, tolerate 429/503. Reuses the
existing `fixtures.ts` (`login` helper + consent pre-dismiss) and `playwright.staging.config.ts`.

**Layer B — API contract sweep (Python `httpx`).** Extend the model of
`apps/api/scripts/staging_smoke.py`: non-destructive endpoint coverage as the demo user; LLM probes
gated + 429/503-tolerant. Already exists and exits 0 today — run it, extend only if a gap is found.

**Layer C — fresh-user / multi-language / account-lifecycle driver (net-new). Requires the
service-role secret.** Admin-creates ≥2 **pre-confirmed** throwaway users (unique emails) via the
Supabase Auth Admin API, drives each through the **full 2-language loop** in the browser (register-
equivalent → login → add lang A+B → generate/save/study each → switch languages → discover → settings
→ logout → log back in → **delete account**), and **deletes every created user in a `finally`**. This
is the core of "mock users learning 2+ languages". Reuse the helper shape from
`apps/api/tests/supabase_auth.py` (`create_confirmed_user` / `login` / `delete_user`); a small TS twin
is needed for the browser specs to mint+clean users with the service-role key.

---

## 4. Canonical end-to-end flow (the script every user-scenario follows)

The precise, file-verified, ordered steps + exact selectors are in **SYNTHESIS.md → Blocker 4**
(22 steps). Summary: land signed-out → log in → add language A (set CEFR) → confirm CEFR band → enter
unique words → generate → save → study A (recognition: reveal + rate "Again" to advance; production:
reveal + tap-a-word explain) → add language B → **switch between A and B** (CEFR band flips) → study B
(RTL/nikkud asserts for Hebrew) → discover → settings save → logout → log back in → (throwaway users
only) delete account. "Back" = nav-away/return or session restart (review is forward-only).

---

## 5. Non-negotiable guardrails (bake these into every spec/driver)

From SYNTHESIS Blockers 2, 3, 7 — violating these causes false failures or pollutes shared staging:

1. **Grade only "Again"** in review — never deplete the shared demo deck.
2. **Throttle LLM actions** (respect 10/min per user); **honor `Retry-After`**; **treat 429/503 as
   acceptable** on LLM steps (the cost guard firing correctly is a PASS).
3. **Tiny, timestamp-unique word lists** (1–2 words) so repeat runs never collide on a shared deck.
4. **Generate-heavy steps use the demo user** (a day-0 fresh user can only generate **5×**). For fresh
   users, keep generation minimal or expect/accept the day-0 cap.
5. **Real-LLM parallelism ≤ 3–4 distinct users**; keep total successful LLM calls **well under the
   global 1000/day** kill-switch (it's project-wide — a runaway loop blocks all staging users until UTC
   midnight).
6. **`DELETE /account` only against throwaway admin-created users — NEVER the demo account.** A partial
   failure is a retryable **502**, not a hard fail.
7. **Clean up everything** created (users, throwaway languages) in `finally`.
8. **No heavy generation load test against live staging** — that belongs on the FakeLLM ephemeral stack
   (out of scope here).
9. **Pre-dismiss the consent banner** (`localStorage['lengua.analytics-consent']='denied'` via
   `addInitScript`) before first navigation — already handled by `fixtures.ts`.

---

## 6. Tooling decision

- **Playwright is primary and sole browser driver.** It is already the entire browser-test stack, with
  a staging-ready config (`playwright.staging.config.ts`), shared login/consent fixtures, and the full
  selector vocabulary. New staging specs drop straight into `apps/web/e2e-staging/`.
- **Do NOT introduce Selenium.** Its only pitch — cross-browser — is already first-class in Playwright:
  add `firefox` + `webkit` to the `projects` array in `playwright.staging.config.ts` (currently
  chromium-only) and the same specs run on all three engines. Selenium would duplicate helpers, run
  slower, and lose trace/screenshot-on-failure. (Cross-browser is **optional** for this validation.)

---

## 7. The build → run → collect → fix → re-run loop (steps 2–5)

Run as a **single Workflow** (deterministic loop + parallel fan-out of fixes) — see RUN.md rationale.

```
PHASE 0 (build): read SYNTHESIS.md + this plan. Author/extend the harness:
  - Layer A: a full-flow staging spec set in apps/web/e2e-staging/ (happy path §4, demo user,
    LLM steps gated behind STAGING_INCLUDE_LLM).
  - Layer C: the fresh-user/multi-language/account-lifecycle driver + a TS admin-user helper
    (create_confirmed_user / delete_user twin) — only wired to run when the service-role secret is set.
  - Layer B: confirm staging_smoke.py runs; extend only on a found gap.

LOOP (max 5 rounds, then PAUSE for human review):
  RUN   : execute Layer B (smoke) + Layer A & C (playwright staging) against live staging.
  COLLECT: write FAILURES-<round>.md — every failure/error with: scenario, expected, actual,
           suite, repro command, suspected cause, and whether it's a product bug vs a test/guardrail
           bug (e.g. an un-throttled 429 = test bug; a 500 or wrong card order = product bug).
  GATE  : if zero real failures (cost-guard 429/503 on LLM steps don't count) → GREEN, stop.
  FIX   : fan out one fix-agent per failure cluster (parallel). Product bugs → fix apps/api or
          apps/web on a branch; test/guardrail bugs → fix the spec/driver. Keep the legacy Streamlit
          app runnable; respect repo verify gates.
  re-run COLLECT/GATE.

FINISH: write VALIDATION-REPORT.md (final PASS/FAIL table per scenario, what was fixed, what was
        skipped + why, leftover risks) and ensure all test users/data are cleaned up.
```

**Iteration cap:** stop and report after 5 fix→re-run rounds even if not fully green, so it can't loop
forever. Sensitive fixes (migrations, security/cost-guard, auth) **pause for human review** — they are
not self-merged.

---

## 8. Prerequisites & run commands

See **RUN.md** for the exact secrets to export (two tiers) and the prompts. Quick reference:

```bash
# Layer A/B (Tier A — demo user, no service-role secret needed beyond the anon key):
cd apps/web && corepack pnpm install && corepack pnpm exec playwright install chromium
PLAYWRIGHT_TEST_BASE_URL=https://lengua-staging.vercel.app STAGING_INCLUDE_LLM=1 corepack pnpm test:e2e-staging

cd apps/api && STAGING_SUPABASE_ANON_KEY=<staging anon key> uv run python scripts/staging_smoke.py
#   add --no-llm to skip the real-Groq probes

# Layer C (Tier B — fresh users / multi-language / delete-account) additionally needs:
#   SUPABASE_STAGING_URL, SUPABASE_STAGING_ANON_KEY, SUPABASE_STAGING_SERVICE_ROLE_KEY
```

---

## 9. Deliverables produced by the run

- `apps/web/e2e-staging/*.spec.ts` — the full-flow staging specs (Layers A + C).
- A fresh-user/multi-language driver + TS admin-user helper (Layer C).
- `planning/staging-validation/FAILURES-<round>.md` — per-round failure reports.
- `planning/staging-validation/VALIDATION-REPORT.md` — the final go/no-go report.
- Any product/test fixes as PRs (low-risk self-merged; sensitive ones paused for review).
