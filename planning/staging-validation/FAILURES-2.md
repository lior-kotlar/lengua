# Round 2 — fix + live re-validation

Round 1 paused on the product blocker (sign-up 500) before fixing the two harness bugs. This round
applies the **test/harness fixes** (no product code, no deploy), re-runs everything against LIVE
staging, and re-confirms the product blocker is unchanged.

**Result: every suite GREEN except the unchanged `signup` product blocker.** Full Playwright suite =
**9 passed / 1 failed** (the 1 failure is PRODUCT_BUG #1); Layer B smoke = **14 / 0 / 0, exit 0**.

Run against LIVE staging (`https://lengua-staging.vercel.app`, API
`https://lengua-api-staging-cxiyhzhria-ew.a.run.app`, Supabase `rydclyotzdwcbbeyitcx`),
`STAGING_INCLUDE_LLM=1`, Tier B (service-role present).

---

## Fixes applied (harness/spec only — low-risk, never runs in CI)

### TEST_BUG #2 — review end-state locator → FIXED
- Files: `apps/web/e2e-staging/full-flow.spec.ts` + `apps/web/e2e-staging/fresh-user-lifecycle.spec.ts`
  (`walkReviewGradingAgain`).
- Change: `done` was `getByRole('heading', { name: 'Done for today' })`, but `SessionComplete`
  (`Review.tsx:447`) renders that text via `<CardTitle>` = a `<div>` (not a heading). Replaced with the
  unique, role-stable **"Check for more" button** (`getByRole('button', { name: 'Check for more' })`),
  verified to exist in `SessionComplete` (`Review.tsx:455`).
- Re-validated: full-flow + both fresh users now reveal/grade and detect the end-of-batch state on small
  decks (the case that bit before).

### TEST_BUG #3 — re-login asserted the Dashboard heading → FIXED
- Files: `apps/web/e2e-staging/fixtures.ts` (`login`) + `apps/web/e2e-staging/fresh-user-lifecycle.spec.ts`
  (`loginAs`).
- Change: a login that follows a sign-out **from `/account`** is correctly returned to `/account`
  (`RequireAuth` stores `state.from` — `route-guards.tsx:53`; `RedirectIfAuthed` restores it), so it does
  not land on the Dashboard. Replaced the `Dashboard` heading assertion with the **Primary navigation**
  (`getByRole('navigation', { name: 'Primary' })`) — the shell marker present on every signed-in screen
  (`app-layout.tsx:40`). Strictly more permissive, so the existing demo specs stay green.
- Re-validated: both fresh users complete sign-out → re-login → **UI delete-account** (the destructive
  step that was previously blocked one step upstream).

### TEST_BUG #4 — silent cleanup leak (found during re-validation) → FIXED
- File: `apps/web/e2e-staging/full-flow.spec.ts` (`removeLanguageIfPresent`).
- Symptom: full-flow PASSED but still **leaked its throwaway languages** (guardrail #7 violation). No
  error was logged, which isolated the cause to the early-return branch.
- Root cause: the helper checked `trigger.count() === 0` immediately after a fresh `goto('/languages')`,
  but the languages list loads from a **separate async query**, so the row hadn't rendered yet → it
  raced the load, saw zero rows, and returned early without removing (or erroring). (In isolation the
  remove flow worked, because the just-added row was already in the query cache.)
- Change: wait for the row to be visible (bounded 15s) before deciding it is absent; only a sustained
  absence falls through to a graceful return.
- Re-validated: post-fix full-flow **self-cleans** its throwaway languages — the full suite left **zero
  leaks** (verified via `GET /languages` as demo + the Auth Admin user list).

---

## Re-validation results (live staging)

| Suite | Round 1 | Round 2 (post-fix) |
|---|---|---|
| Layer B — `staging_smoke.py` (with LLM) | 14 / 0 / 0, exit 0 | **14 / 0 / 0, exit 0** (`/generate`, `/discover` 200) |
| Layer A — `full-flow.spec.ts` (demo journey) | FAIL (#2) | **PASS** (self-cleans) |
| Layer C — `fresh-user-lifecycle.spec.ts` ×2 | FAIL (#3) | **PASS ×2** (incl. UI delete-account) |
| Layer A — `signup.spec.ts` | FAIL (PRODUCT_BUG #1) | **FAIL — unchanged** (product blocker) |
| `auth.spec.ts` ×2 + `screens.spec.ts` ×4 | PASS | **PASS** |
| **Full Playwright suite** | 6 pass / 3 fail / 1 didn't-run | **9 pass / 1 fail (signup)** |

No cost-guard throttles fired in either round (every `/generate`, `/discover`, `/cards/save` returned
200). Each fixed spec was also re-run individually and statically re-checked (prettier / eslint / tsc on
`tsconfig.e2e-staging.json` + base / `playwright --list`) — all clean.

---

## Remaining blocker (unchanged from round 1)

**PRODUCT_BUG #1 — public sign-up returns HTTP 500** `{"code":"unexpected_failure","message":"Error
sending confirmation email"}` from Supabase Auth (`POST /auth/v1/signup`). Reproduced again this round.
It is a **Supabase staging Auth email/SMTP config** problem (infra/config fix + redeploy + human
review) — not fixable by editing a spec, and not self-merged per the autonomous protocol. Full detail
+ the secondary `{}`-alert UX follow-up: `FAILURES-1.md` and `VALIDATION-REPORT.md` §4.

## Cleanup

Zero leaks after the full suite: the demo account holds only its two legitimate languages
(Spanish + Hebrew); no `lengua-val-*` / `lengua-signup-*` auth users remain. The harness now self-cleans
(TEST_BUG #4 fix); the external sweep found nothing left to remove on the final pass.
