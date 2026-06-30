# Round 1 — Live-staging validation failures

**Verdict: NOT GREEN.** 3 real failures (1 PRODUCT_BUG, 2 TEST_BUG) + 1 "did not run" (serial
abort). No cost-guard throttles fired (every `/generate`, `/discover`, `/cards/save` returned 200).

Run against LIVE staging (`https://lengua-staging.vercel.app`, API
`https://lengua-api-staging-cxiyhzhria-ew.a.run.app`, Supabase `rydclyotzdwcbbeyitcx`).
`STAGING_INCLUDE_LLM=1`.

## Suite results (canonical round-1 runs)

| Suite | Result |
|---|---|
| Layer B — `staging_smoke.py` (demo) | **14 passed, 0 failed, 0 skipped** — exit 0 |
| Layer A/C 2a — full-flow, signup, auth, screens | **6 passed, 2 failed** (full-flow, signup) |
| Layer A/C 2b — fresh-user-lifecycle (serial) | **0 passed, 1 failed** (user 1), **1 did not run** (user 2) |

Every failure was **reproduced** in a second serial run (full-flow + signup), so none is a one-off
flake. Diagnosis used the failure `error-context.md` accessibility snapshots and the captured
Playwright network traces.

---

## FAILURE 1 — PRODUCT_BUG — public sign-up returns HTTP 500 (email send fails) ⚠️ PRIORITY

- **Suite / test:** `signup.spec.ts:22` — "a visitor can submit the sign-up form and see the
  verification notice".
- **Scenario:** Drive the real `/signup` form with a unique disposable email + policy-valid
  password, click "Create account", expect the "Check your email" verification notice.
- **Expected:** Form is replaced by the `Check your email` heading echoing the address.
- **Actual:** Form stays; an empty error alert (`{}`) is shown. The underlying GoTrue call
  **`POST https://rydclyotzdwcbbeyitcx.supabase.co/auth/v1/signup` returned HTTP 500** with body:
  ```json
  {"code":"unexpected_failure","message":"Error sending confirmation email"}
  ```
  Response header `x-sb-error-code: unexpected_failure`. (Evidence: signup trace
  `0-trace.network` + response resource — preserved in scratchpad `trace-signup/`.)
- **Reproduced:** 4/4 attempts across two runs ~1h apart (22:36 and 23:23) → **sustained**, not a
  transient blip or a short rate-limit window.
- **Verdict — PRODUCT_BUG (do NOT fix here):** This is a deployed-app HTTP 500 from Supabase Auth:
  staging cannot send confirmation emails, so **public email sign-up is broken end-to-end** — a real
  new user signing up right now gets this 500. It is NOT a 429/503 LLM cost-guard (so not COST_GUARD),
  and it cannot be made green by editing the spec without hiding a genuine availability defect.
- **Suspected cause / source:** Supabase **staging Auth email/SMTP configuration** (confirmation-email
  delivery is failing — SMTP misconfig, exhausted/absent email provider, or email quota). This is an
  infra/config fix on the Supabase project, NOT an `apps/*` code file. Call site is
  `apps/web/src/lib/auth.ts` → `signUpWithEmail` (the form handled the error correctly).
- **Secondary (minor) UX bug, same screen:** the 500 `unexpected_failure` surfaces as an unhelpful
  `{}` alert. `mapAuthError` (`apps/web/src/lib/auth.ts:49`) falls through to the default case and the
  error message renders as `{}` instead of a friendly line. Not the root cause; worth a follow-up.
- **Repro:**
  ```bash
  cd apps/web && source <staging-secrets.env> && corepack pnpm exec playwright test \
    --config playwright.staging.config.ts signup.spec.ts --workers=1 --reporter=list
  ```

---

## FAILURE 2 — TEST_BUG — review walk can't detect the "Done for today" end-state

- **Suite / test:** `full-flow.spec.ts:196` — "demo user completes the full learning journey across
  two languages" → step **"Study A — reveal, tap-a-word, grade Again (LLM-gated)"** (helper
  `walkReviewGradingAgain`, line 124).
- **Scenario:** After generate+save for the throwaway language A, navigate to Review and walk the
  deck grading only "Again", stopping at the end-of-batch state.
- **Expected:** The walk reveals/grades each card, then detects the end state (reveal button,
  "Done for today", or empty-state) and stops.
- **Actual:** 20s timeout on `expect(reveal.or(done).or(empty)).toBeVisible()`. The failure
  `error-context.md` snapshot shows the Review main content **IS** showing the SessionComplete
  end-state: `text: Done for today  You reviewed 2 cards. Nice work.` + "Check for more" + "Generate
  more". The walk graded both cards successfully and reached the legit end-of-batch — it just can't
  SEE it.
- **Root cause:** the `done` locator is `getByRole('heading', { name: 'Done for today' })`, but
  `SessionComplete` (`apps/web/src/pages/Review.tsx:447`) renders "Done for today" via `<CardTitle>`,
  which is a **`<div>`** (`apps/web/src/components/ui/card.tsx:32-45`) — **not** a heading and with no
  `role="heading"`. So the locator never matches.
- **Why it triggers only sometimes:** the bug fires only when `batch.length < maxCards` (4). Real-Groq
  generation is non-deterministic: the demo word produced **1 sentence = 2 cards** (walk hits
  SessionComplete at iteration 2 → fail), whereas the fresh user's word produced **3 sentences = 6
  cards** (walk grades 4 and exits the loop before SessionComplete → that spec PASSED Study A). This
  is why the same helper passes on big decks and fails on small ones.
- **Verdict — TEST_BUG.** The product flow (generate → save → review → grade Again → SessionComplete)
  works correctly; only the test's end-state locator is wrong.
- **Fix file(s):** `apps/web/e2e-staging/full-flow.spec.ts` (`walkReviewGradingAgain`, the `done`
  locator ~line 119) — and the identical helper in
  `apps/web/e2e-staging/fresh-user-lifecycle.spec.ts` (~line 154). Match the actual DOM, e.g.
  `page.getByText('Done for today')` or the "Check for more" button (or give SessionComplete's title a
  heading role / `data-testid`).
- **Repro:**
  ```bash
  cd apps/web && source <staging-secrets.env> && corepack pnpm exec playwright test \
    --config playwright.staging.config.ts full-flow.spec.ts --workers=1 --reporter=list
  ```

---

## FAILURE 3 — TEST_BUG — re-login after sign-out lands on /account, not Dashboard

- **Suite / test:** `fresh-user-lifecycle.spec.ts:255` — "fresh user 1 completes the two-language
  lifecycle then deletes the account" → step **"Log back in → languages (and their decks) survived"**
  (helper `loginAs`, line 87).
- **Scenario:** The journey goes Account → sign out (→ `/login`) → log back in, then expects the
  Dashboard.
- **Expected:** `loginAs` waits for `getByRole('heading', { name: 'Dashboard' })` after login.
- **Actual:** 20s timeout. The failure snapshot shows the user **fully authenticated** (banner email,
  both languages in the picker, full nav) but on the **Account** page (`heading "Account"`), not the
  Dashboard.
- **Root cause (app behaving as designed):** Sign-out from `/account` clears the session; `RequireAuth`
  redirects to `/login` with `state.from = /account`
  (`apps/web/src/components/route-guards.tsx:53`). The helper then does `page.goto('/login')` — a
  same-URL reload that **preserves `window.history.state`** — so React Router still has
  `location.state.from = /account`. After login, `RedirectIfAuthed`
  (`route-guards.tsx:59-77`) correctly returns the user to the originally-requested location
  (`/account`), which is the documented behavior ("preserve the FULL originally-requested location").
  The FIRST login in the same test passes because it starts with no `from` state.
- **Verdict — TEST_BUG.** The account/data all survived; the journey is functionally fine. The helper's
  assumption that re-login always reaches the Dashboard is the flaw (a latent bug shared with the demo
  `login` fixture, which would hit the same on its "Log back in" step).
- **Fix file(s):** `apps/web/e2e-staging/fresh-user-lifecycle.spec.ts` (`loginAs`, line 87) and
  `apps/web/e2e-staging/fixtures.ts` (`login`, line 45). After login, assert the authenticated shell
  generically (e.g. the Primary `navigation`, or the banner "Sign out" button) instead of the
  "Dashboard" heading — or clear history state / navigate to a known route before asserting.
- **Knock-on:** "fresh user 2" **did not run** — `fresh-user-lifecycle` is `mode: 'serial'`, so the
  group aborts after user 1 fails. Not an independent failure.
- **Repro:**
  ```bash
  cd apps/web && source <staging-secrets.env> && corepack pnpm exec playwright test \
    --config playwright.staging.config.ts fresh-user-lifecycle.spec.ts --workers=1 --reporter=list
  ```

---

## Cost-guard events

**None.** Every LLM-touching call observed returned HTTP 200 — smoke `/generate` + `/discover`; the
full-flow demo generates (cards saved, `savedA=true`); the fresh-user `/generate`, `/cards/save`,
`/discover` (all 200, verified in the trace). No 429/503/daily-limit/rate-limit was surfaced as a
failure, so there is nothing to tolerate and no COST_GUARD reclassification.

## Leaks observed (pollution to clean up)

The full-flow `finally` cleanup did **not** remove its throwaway languages after the Study A failure.
**4 throwaway languages leaked on the demo account** (confirmed via `GET /languages` as demo):

| id | name |
|---|---|
| 16 | `ZZval-A-1782850391703` |
| 17 | `ZZval-A-1782850439659` |
| 22 | `ZZval-A-1782850858818` |
| 23 | `ZZval-A-1782850888737` |

Each carries ~2 saved cards. They need cleanup (`DELETE /languages/{id}` as the demo user — cascades
their cards; never touches the seeded Spanish/Hebrew). Fixing FAILURE 2's `done` locator should also
stop the leak (the journey would complete and clean up from a healthy page state).

Fresh-user throwaway **users + their languages** were admin hard-deleted (cascade) by the spec's
`afterAll` (no leak there). The signup attempts created **no** leaked `auth.users` row (the 500 rolled
back the sign-up; `afterAll` admin-cleanup also ran).
