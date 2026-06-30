# RUN — how to execute the staging validation

Everything is planned in [`VALIDATION-PLAN.md`](VALIDATION-PLAN.md) + [`research/SYNTHESIS.md`](research/SYNTHESIS.md).
This file is **what you actually do**: set secrets, then paste **one prompt** into a fresh Claude Code
session. The run builds the harness, then loops run → fix → re-run until staging is green.

---

## Step 0 — set secrets (once, in the terminal you'll launch Claude from)

There are **two tiers**. Tier A needs nothing but the staging anon key. Tier B unlocks the full
"fresh mock users, 2+ languages, register/logout/login, delete account" ask.

```bash
# ---- Tier A (demo-user full loop + signup-form UI) ----
export STAGING_SUPABASE_ANON_KEY="<staging Supabase anon key>"   # browser-safe; from Supabase dash or GH secret SUPABASE_STAGING_ANON_KEY
export STAGING_INCLUDE_LLM=1                                      # exercise generate/save/review/discover (throttled; ~$0 on Groq free tier)

# ---- Tier B (adds fresh mock users + delete-account; recommended for the full ask) ----
export SUPABASE_STAGING_URL="https://rydclyotzdwcbbeyitcx.supabase.co"
export SUPABASE_STAGING_ANON_KEY="<same staging anon key as above>"
export SUPABASE_STAGING_SERVICE_ROLE_KEY="<staging service-role key>"   # SECRET — never commit/echo to a PR. Supabase dash → Project Settings → API, or GH secret SUPABASE_STAGING_SERVICE_ROLE_KEY
```

Where to get them: **Supabase dashboard** → project `rydclyotzdwcbbeyitcx` → Project Settings → API
(anon + service_role keys), or your GitHub repo **Actions secrets** (`SUPABASE_STAGING_ANON_KEY`,
`SUPABASE_STAGING_SERVICE_ROLE_KEY`). The demo creds (`demo@lengua.test` / `demo-password-123`) are
already the defaults — no need to set them.

> If you only set Tier A, the run still validates the **entire learning loop** as the demo user and the
> signup-form UI; it will clearly report the fresh-user/multi-user/delete-account scenarios as SKIPPED.
> Set Tier B to actually run those.

---

## Step 1 — paste THIS prompt into a fresh Claude Code session

(Start fresh — `claude` in `C:\Users\yulin\repos\lengua`. The prompt is self-contained; it points the
session at the plan files.)

> **PROMPT — copy everything between the lines:**

---
ultracode

Validate that a real user can complete the FULL learning flow on live staging
(https://lengua-staging.vercel.app) and that staging is ready for users. Do NOT change the product's
behavior except to fix genuine bugs the validation uncovers.

First read these (already written — do not redo the recon):
- planning/staging-validation/VALIDATION-PLAN.md
- planning/staging-validation/research/SYNTHESIS.md   (the 7 blockers, the 22-step flow, exact selectors)

Then run the build → run → collect → fix → re-run loop from VALIDATION-PLAN.md §7 as a single
Workflow (deterministic loop + parallel fix fan-out):

PHASE 0 — build the harness:
- Layer A: author full-flow Playwright staging specs in apps/web/e2e-staging/ covering the §4 / Blocker-4
  flow as the demo user (login → add language A + CEFR → enter unique words → generate → save → study A
  recognition+production incl. reveal, rate "Again" to advance, tap-a-word explain → add language B →
  SWITCH between languages via the header "Active language" picker (assert CEFR band flips) → study B
  (RTL/nikkud for Hebrew) → discover → settings save → logout → log back in). Gate every LLM-touching
  step behind env STAGING_INCLUDE_LLM. Reuse e2e-staging/fixtures.ts (login + consent pre-dismiss) and
  playwright.staging.config.ts. Also add a signup-FORM spec (fill + assert "Check your email"; do not
  try to confirm — public confirmation can't be automated).
- Layer C (only when SUPABASE_STAGING_SERVICE_ROLE_KEY is set): a fresh-user / multi-language /
  account-lifecycle driver that admin-creates >=2 pre-confirmed throwaway users (unique emails) via the
  Supabase Auth Admin API (mirror apps/api/tests/supabase_auth.py: create_confirmed_user / login /
  delete_user — write a small TS twin for the browser specs), drives each through the full 2-language
  loop, then DELETES every created user in a finally. If the secret is absent, SKIP Layer C and say so.
- Layer B: confirm apps/api/scripts/staging_smoke.py runs (exit 0); extend only if you find a real gap.

LOOP (max 5 rounds, then PAUSE and report):
- RUN all suites against live staging.
- COLLECT every failure into planning/staging-validation/FAILURES-<round>.md (scenario, expected,
  actual, suite, exact repro command, suspected cause, and product-bug vs test/guardrail-bug).
- GATE: if there are zero REAL failures, stop — green. A cost-guard 429/503 on an LLM step is a PASS,
  not a failure (do not "fix" the cost guard).
- FIX: fan out one agent per failure cluster in parallel. Product bugs → fix apps/api or apps/web on a
  branch; test/guardrail bugs → fix the spec/driver. Then re-run.

HARD GUARDRAILS (from VALIDATION-PLAN.md §5 — violating these causes false failures or pollutes
staging): grade ONLY "Again" in review; throttle LLM and honor Retry-After; tiny timestamp-unique word
lists; generate-heavy steps use the demo user (fresh users only get 5 generates day-0); real-LLM
parallelism <=3-4 distinct users and total successful LLM calls well under 1000/day; DELETE /account
ONLY against throwaway users, NEVER demo; clean up every created user/language in finally; do NOT run a
heavy generation load test against live staging.

Repo rules: trunk-based — branch off main, PR + self-merge only LOW-RISK green changes, 0 approvals;
PAUSE for human review on sensitive fixes (migrations, security/cost-guard, auth, architectural). Keep
the legacy Streamlit app runnable. Run each app's verify gate before merging a fix.

FINISH: write planning/staging-validation/VALIDATION-REPORT.md — a per-scenario PASS/FAIL/SKIP table,
what was fixed, what was skipped + why, leftover risks, and a clear GO / NO-GO verdict on
"staging is ready for users". Confirm all test users/data were cleaned up.
---

That's it — let it run. It will pause only if it hits a sensitive fix or 5 rounds without going green.

---

## (Fallback) per-step prompts — if you'd rather drive it manually

Use these only if you don't want the single looping prompt above.

- **Step 1 — build harness:** "Read planning/staging-validation/VALIDATION-PLAN.md and research/SYNTHESIS.md.
  Build the Layer A + Layer C + Layer B harness exactly as described (PHASE 0). Don't run it yet — just
  author the specs/driver/helper and show me the file list."
- **Step 2 — run + collect:** "Run all three layers against live staging with the guardrails in §5.
  Write every failure to planning/staging-validation/FAILURES-1.md (scenario, expected, actual, repro,
  product-bug vs test-bug). Don't fix anything yet."
- **Step 3 — fix:** "Fix every item in FAILURES-1.md — fan out parallel agents, one per cluster. Product
  bugs in apps/api/apps/web on a branch; test/guardrail bugs in the specs. PR + self-merge low-risk
  green; pause for review on sensitive fixes."
- **Step 4 — re-run:** "Re-run all layers; write FAILURES-2.md. If green, write VALIDATION-REPORT.md."
- **Step 5 — loop:** repeat Step 3 → Step 4 with the next-numbered FAILURES file until green (cap 5).

---

## Manual smoke (optional — verify your secrets work before the big run)

```bash
cd apps/api && STAGING_SUPABASE_ANON_KEY="$STAGING_SUPABASE_ANON_KEY" uv run python scripts/staging_smoke.py --no-llm
#   expect: a PASS table and exit 0. Add (drop --no-llm) to also probe generate/discover (429/503 = PASS).
```
