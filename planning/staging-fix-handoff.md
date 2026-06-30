# Live-staging fix pass — handoff / resume state (2026-06-30)

**What this is:** the resume point for the live-staging correctness fix pass (the 25-finding triage in
[`staging-validation.md`](staging-validation.md)). The multi-agent fix workflow ran; this captures
exactly what merged, what's open, and the **light driver-only steps that remain**.

## TL;DR — decision
- **No more heavy multi-agent runs are needed.** The only agent still in flight is **S1 (erasure)**,
  which only opens a PR that **pauses for owner review** (never self-merges).
- Everything else left is **lightweight driver work**: confirm CI green on 3 PRs, diagnose one
  backend-test failure, merge serially, then re-validate + update docs.
- A fresh session can finish this from the **Remaining steps** section below.

## ✅ Merged to `main` (done)
| Finding | PR | What |
|---|---|---|
| S4 | #79 | idempotent `seed-staging.yml` (dispatched + verified: demo deck = 12 ES + 6 HE/RTL cards) |
| S5 | #82 | web Sentry `VITE_SENTRY_ENVIRONMENT` + `VITE_SENTRY_TRACES_SAMPLE_RATE` |
| S8, S15 | #84 | discover reroll cache-bypass (`fresh` flag) + never-cache-empty + known-word filter |
| S2 | #85 | OAuth default → Google-only (Apple button no longer dead-ends) |
| S6, S13, S19 | #86 | review due-first + recognition answer plain text (RTL) + kind-agnostic limit copy |
| (tooling) | #87 | reusable validators: `apps/api/scripts/staging_smoke.py` + `apps/web/e2e-staging/` + `playwright.staging.config.ts` (kept OUT of CI gates) |

## ✅ Diagnosed, no code change
- **S21** (recurring WARNING logs) = **benign**. They're Cloud Run *platform request logs*
  auto-tagged WARNING for 4xx — unauthenticated `curl/8.8.0` probes (the validation pass's own)
  getting expected `401` on `/me` + `/experimental/word-of-the-day`, and a malformed `OPTIONS`
  preflight `400`. Not application warnings. Mark `fixed`/benign in the triage.

## ⏸ PAUSED for owner review — do NOT self-merge
- **#83** — S16 (CORS `expose_headers=[Retry-After]`) + S17 (API security-headers middleware +
  `apps/web/vercel.json` headers + baseline CSP). **CI is green.** The auto-mode classifier correctly
  blocked self-merge per the pause-on-security/CORS boundary. **Owner (Ben/Kotlar): review the CSP**
  (`connect-src` = self, `*.supabase.co`, `*.run.app`, `*.sentry.io`, PostHog) and merge. CD is gated
  off, so the `vercel.json` CSP cannot reach live staging until CD is armed.
- **#91** — S1 erasure. `fix/s1-account-erasure-cascade`. Guarded+idempotent Alembic `0006`
  (`profiles.id → auth.users(id) ON DELETE CASCADE`, `down_revision=0005`) + a **profiles-first**
  two-step delete in the account service (privileged profiles delete, then GoTrue admin delete) +
  an erasure integration test that proves all domain rows are erased **even when the FK cascade
  can't run**. Local verify green (ruff/format/mypy, 19 account tests, openapi byte-identical,
  migration-drift GREEN). **PAUSES** (migration). Owner must: (a) review — note `0006` deletes
  pre-existing orphan `profiles` rows (`WHERE NOT EXISTS auth.users`) before `VALIDATE`, i.e. a data
  deletion inside a migration (correct GDPR remediation, flagged in the migration); (b) merge; (c)
  apply to live DBs: `cd apps/api && uv run alembic -x env=staging upgrade head` then `-x env=prod`.
  NOTE: #91 already edited `staging-validation.md` + `outstanding-work.md` to mark S1 fix-PR-open, so
  reconcile the final doc-status update with #91 (do it after #91 merges, or coordinate the edits).

## 🟡 Open PRs needing finish (format fixes already pushed)
All three failed CI **only on formatting** (my agent fast-checks omitted `ruff format --check` /
`prettier --check`). I pushed the format fixes; **verify CI is now green**, then merge.

| PR | Findings | Format fix pushed | Other CI issue |
|---|---|---|---|
| #88 | S3, S12, S14 (languages) | ✅ prettier (`add-language-form.tsx`) `bff88fd` | ⚠ **also failed `backend tests + coverage`** — diagnose (below) |
| #89 | S7, S11 (generate) | ✅ ruff format `cec970e` | none seen (drift was CLEAN) |
| #90 | S9, S10 (settings) | ✅ ruff format `fb6a428` | verify (contract PR) |

These are MEDIUM risk (data-loss fix / schema changes) but are in the **agent self-merge batch** per
the task scope (unlike #83 security) — merging is intended once green.

## Remaining steps (ordered)
1. **Diagnose #88's `backend tests + coverage` failure.** The local Supabase DB is now migrated (an
   agent ran `supabase db reset`), so reproduce locally. From the #88 worktree
   (`.claude/worktrees/agent-a1fbe294ba4feeec3`) or a fresh checkout of `fix/s3-s12-s14-languages`:
   ```
   cd apps/api && uv run pytest tests/api/test_languages.py tests/services/test_languages_service.py tests/repositories/test_languages_repo.py -q
   ```
   Likely a **cross-cutting test** that `POST /languages` and asserts the OLD response shape (it now
   returns `LanguageCreateOut` with a `created` flag, still HTTP 200), OR a **coverage dip** on the
   new code. Grep for other callers: `rg "POST.*/languages|post\(.*languages|/languages\"" apps/api/tests`.
   Fix + push. (If a coverage dip: run the full `uv run pytest` and add tests for the uncovered
   branches in `app/services|schemas|repositories/languages.py`.)
2. **Confirm CI green** on #88, #89, #90: `gh pr checks <n> --json bucket -q '[.[].bucket]|group_by(.)|map("\(.[0])=\(length)")|join(" ")'`.
3. **Merge serially** (squash), one at a time, re-checking `main` stays green:
   `gh pr merge <n> --squash`. They're contract PRs (`openapi.json` + `packages/api-types/src/schema.ts`)
   but touch **disjoint** routes (`/languages`, `/generate`, `/settings`) so GitHub auto-3-way-merges
   them (each was `MERGEABLE`). **If a conflict appears** on the generated files, rebase the branch on
   `main` and regenerate instead of hand-merging:
   ```
   cd apps/api && uv run python scripts/dump_openapi.py
   corepack pnpm --filter api-types generate     # pnpm not on PATH; corepack pnpm = 9.15.0
   git add apps/api/openapi.json packages/api-types/src && git rebase --continue && git push --force-with-lease
   ```
4. **S1**: when the agent finishes, confirm its PR is open (`gh pr list`); **leave it paused**; add
   the owner note (review + apply migration to staging/prod).
5. **Final re-validation** (after the merges land on `main`):
   - API smoke: `cd apps/api && STAGING_SUPABASE_ANON_KEY=<staging anon key> uv run python scripts/staging_smoke.py`
     (anon key = GH secret `SUPABASE_STAGING_ANON_KEY` or the Supabase dashboard → project
     `rydclyotzdwcbbeyitcx` → API settings).
   - Browser: `cd apps/web && PLAYWRIGHT_TEST_BASE_URL=https://lengua-staging.vercel.app npm run test:e2e-staging`.
   - Spot-check logs: the `gcloud logging read … service_name="lengua-api-staging" … --freshness=1h` query.
6. **Doc updates** (small PR to `main`, or fold into a docs commit):
   - `planning/staging-validation.md`: set **Status → fixed** for S2, S4, S5, S6, S7, S8, S9, S10,
     S11, S12, S13, S14, S15, S19, and S21 (benign). Mark **S1, S16, S17** as "fix PR open — paused
     for owner". S18, S20 remain owner.
   - `planning/outstanding-work.md` §0: tick the fixed rows; note S1/S16/S17 paused; S18/S20 owner.
7. **Surface owner items** (do NOT do — list for Ben/Kotlar):
   - **S2** — set `VITE_OAUTH_PROVIDERS` per env + actually enable Apple in Supabase (needs paid
     Apple Developer acct) if Apple is wanted; today's code default hides it.
   - **S18** — confirm the stable Vercel staging alias path (`lengua-staging.vercel.app`).
   - **S20** — confirm intent to gate `/docs` in prod (`docs_url=None` unless env in {local,staging}).
   - **Deferred:** arm `DEPLOY_ENABLED` (CD), Phase-5 observability live-verify (§G), Google OAuth
     creds, Resend SMTP + SPF/DKIM/DMARC.
   - **Review + merge #83** (CSP) and **review + apply S1 migration**.

## Env facts (so the resumed session doesn't re-derive)
- On `main`, `gh` authed as `BenArtzi4` → repo `lior-kotlar/lengua`. Branch protection OFF (can merge
  without approvals). Squash-merge is the convention.
- Staging: web `https://lengua-staging.vercel.app`; API `https://lengua-api-staging-cxiyhzhria-ew.a.run.app`;
  Supabase `rydclyotzdwcbbeyitcx`; demo `demo@lengua.test` / `demo-password-123`. Seed dispatched OK.
- Local Supabase (Docker) is UP and now migrated. `pnpm` is NOT on PATH — use `corepack pnpm`. `npm`
  works (`npm --prefix apps/web run <script>`).
- CI gate (per-PR, all required): `lint + format + types` (incl. ruff-format + prettier + the
  `api-types` drift check), `backend tests + coverage` (≥80%, real Postgres), `frontend tests`,
  `build`, `e2e`, `security`. **Local fast checks MUST include `ruff format --check` (api) and
  `pnpm format:check` (web)** — that's what bit #88/#89/#90.
- Worktrees for the open PRs live under `.claude/worktrees/agent-<id>/` (can be cleaned with
  `git worktree remove` once merged).
