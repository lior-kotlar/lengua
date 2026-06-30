# Owner-deferred tasks (Kotlar) — do at the very end, before launch

These are **owner-only repo-hardening actions** that need GitHub **admin** rights on
`lior-kotlar/lengua` and are **intentionally deferred to the end of the build** (at / just
before the Phase 9 launch). **None of them block any implementation work.** They harden the
trunk and the supply chain *after* the quality gate and deploy pipeline are proven — and turning
branch protection on early would actually break the autonomous PR + self-merge flow the build
relies on (it self-merges low-risk green PRs with 0 approvals).

> **Owner:** Lior Kotlar (repo admin). Ben (`benartzi4@gmail.com`) cannot do these without admin.
> **Status:** deferred — *non-blocking*. When done, tick the matching boxes in
> [`tasks/phase-0-foundations.md`](tasks/phase-0-foundations.md) (`0.6.3`, `0.6.4`).

---

## 1. Branch protection on `main` (was task 0.6.3)

Protect `main`:
- Require a pull request before merging — **1 approval**.
- Require status checks to pass **and** the branch to be up to date (strict). The required-check
  names are the exact contexts listed in [`../infra/branch-protection.md`](../infra/branch-protection.md)
  (written by the Phase 0 CI-gate task `0.6.2`).
- Dismiss stale approvals on new commits.
- Include administrators.

**How (admin):** GitHub → *Settings → Branches → Add branch protection rule* for `main`, or via
API with a JSON body:

```sh
gh api -X PUT repos/lior-kotlar/lengua/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "lint-and-types" }, { "context": "backend-tests" }, { "context": "frontend-tests" }, { "context": "build" }, { "context": "e2e" }, { "context": "security" } ] },
  "required_pull_request_reviews": { "required_approving_review_count": 1, "dismiss_stale_reviews": true },
  "enforce_admins": true,
  "restrictions": null
}
JSON
```

(Replace the `context` values with the actual job/check names from `infra/branch-protection.md`.)

**Verify:** `gh api repos/lior-kotlar/lengua/branches/main/protection` returns without 404 and
shows `required_pull_request_reviews.required_approving_review_count = 1`; a direct push to
`main` is rejected.

**⚠ Sequencing note:** while this is off, the autonomous build self-merges low-risk green PRs
with 0 approvals. Turning it on **ends that** and requires a human (or a second account) to
approve every PR. So enable it **only once the autonomous build is finished**.

---

## 2. Dependabot alerts + automated security fixes (was task 0.6.4)

Enable Dependabot vulnerability alerts and automated security-update PRs.

**How (admin):** GitHub → *Settings → Code security* → enable **Dependency graph**, **Dependabot
alerts**, and **Dependabot security updates**. (Optionally also commit a `.github/dependabot.yml`
for routine version-bump PRs across `apps/api` (uv/pip) and `apps/web` (pnpm).)

**Verify:** `gh api repos/lior-kotlar/lengua/vulnerability-alerts -i` returns HTTP **204** (not 404).

---

## Still-outstanding owner items elsewhere (not deferred — needed by later phases, still non-blocking for Phase 0)

These are tracked in [`tasks/phase-0-foundations.md`](tasks/phase-0-foundations.md) `0.7.x` and
are **not** part of this "do at the end" set, but listing them here for one owner view:

- **`0.7.7` — add CI secrets `GCP_REGION=europe-west1` and `SENTRY_ORG=kotlar-y7`.** Needed by
  the deploy pipeline (Phase 6) and observability (Phase 5); not needed for the Phase 0 CI gate.
- **`0.7.8` — confirm Resend custom SMTP delivers in both Supabase projects.** Needed for auth
  sign-up / recovery emails (Phase 2); staging auto-confirm is OFF.

## Live-staging fix-pass review items (2026-06-30) — owner review/apply

Surfaced by the live-staging validation + fix pass (full triage
[`staging-validation.md`](staging-validation.md); resume state
[`staging-fix-handoff.md`](staging-fix-handoff.md)). These need **owner judgment** and so were NOT
self-merged by the build:

- **Review + merge PR #91 (S1 — right-to-erasure), THEN apply migration `0006`.** `DELETE /account`
  orphaned all of a user's data because the **Alembic-built** staging/prod DB lacks the
  `profiles → auth.users` FK the canonical `supabase/migrations` SQL declares. #91 adds a guarded,
  idempotent migration `0006` (adds the FK + cascade) + a defensive profiles-row delete in the
  service + an erasure integration test. **After merge, apply to the live DBs:**
  `cd apps/api && uv run alembic -x env=staging upgrade head` then `-x env=prod`. ⚠ `0006` deletes
  pre-existing orphan `profiles` rows (`WHERE NOT EXISTS auth.users`) before `VALIDATE` — correct
  GDPR remediation, but it IS a data deletion inside a migration (flagged in the file). Unblocks the
  privacy/right-to-erasure compliance text (Phase 8).
- **Review + merge PR #83 (S16/S17 — security headers).** CORS `expose_headers=[Retry-After]` + an
  API security-headers middleware (nosniff / X-Frame-Options DENY / Referrer-Policy / HSTS) +
  `apps/web/vercel.json` headers + a **baseline CSP**. CI is green; the auto-build held it for owner
  review per the pause-on-security/CORS rule. **Sanity-check the CSP `connect-src`** (self,
  `*.supabase.co`, `*.run.app`, `*.sentry.io`, PostHog) against what the live SPA actually calls
  before it ships (it only reaches the browser once CD is armed / on the next web deploy).
- **S2 — set `VITE_OAUTH_PROVIDERS` per env + enable Apple** (Supabase external provider; needs a
  paid Apple Developer acct) **only if Apple is wanted.** The merged code default is Google-only, so
  the broken Apple button is hidden today; setting `VITE_OAUTH_PROVIDERS=google,apple` re-enables it
  once Apple is configured.
- **S18 — confirm the stable Vercel staging alias** (`lengua-staging.vercel.app`) update path
  (overlaps §C of [`go-live-activation.md`](go-live-activation.md)).
- **S20 — confirm intent to gate prod `/docs` `/redoc` `/openapi.json`** (`docs_url=None` unless env
  in {local,staging}). Acceptable on staging; decide for prod.

(Still deferred + tracked elsewhere: arm `DEPLOY_ENABLED` for CD — go-live §E; Phase-5 observability
live-verify — §G; Google OAuth creds; Resend SMTP + SPF/DKIM/DMARC.)

## Resolved owner items (for the record)

- **`0.7.9` Vercel access — RESOLVED (2026-06-25).** On the **free** tier a project has a single
  manager seat; Ben (`benartzi4@gmail.com`) is the account holder/manager for `lengua`. Not
  blocking — proceeding as-is.
- **`0.7.10` Grafana Cloud + Sentry — DONE (2026-06-25).** Ben joined Grafana Cloud and both
  Sentry projects (lengua-api, lengua-web).
