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

- **`0.7.7` — ☑ DONE (verified 2026-07-05).** CI secrets `GCP_REGION=europe-west1` +
  `SENTRY_ORG=kotlar-y7` are present (`gh secret list`, added 2026-06-25); the armed staging CD
  consumes them green.
- **`0.7.8` — confirm Resend custom SMTP delivers in both Supabase projects.** Needed for auth
  sign-up / recovery emails (Phase 2); staging auto-confirm is OFF.

## Live-staging fix-pass review items (2026-06-30) — ☑ RESOLVED

The live-staging validation + fix pass is complete: **all 22 findings (S1–S22) are fixed or
accepted**, and the two owner-paused PRs landed — **#91** (S1 right-to-erasure: guarded migration
`0006` adding `profiles.id → auth.users(id) ON DELETE CASCADE`, applied to the staging DB) and
**#83** (S16/S17 CORS `Retry-After` expose + security-headers middleware + baseline CSP, verified
live). **S18** stable Vercel alias resolved (#71). Full record:
[`../CHANGELOG.md`](../CHANGELOG.md).

Residual owner follow-ups (still open):
- **S2 — set `VITE_OAUTH_PROVIDERS` per env + enable Apple** (needs a paid Apple Developer acct; the
  merged code default is Google-only, so the broken Apple button is hidden today).
- **S20 — gate prod `/docs` `/redoc` `/openapi.json`** before public launch (accepted on staging).

(Also tracked elsewhere: Phase-5 observability live-verify — [`go-live-activation.md`](go-live-activation.md) §G;
Google/Apple OAuth creds; Resend SMTP + SPF/DKIM/DMARC — see `0.7.8` above + [`outstanding-work.md`](outstanding-work.md).)

## Resolved owner items (for the record)

- **`0.7.9` Vercel access — RESOLVED (2026-06-25).** On the **free** tier a project has a single
  manager seat; Ben (`benartzi4@gmail.com`) is the account holder/manager for `lengua`. Not
  blocking — proceeding as-is.
- **`0.7.10` Grafana Cloud + Sentry — DONE (2026-06-25).** Ben joined Grafana Cloud and both
  Sentry projects (lengua-api, lengua-web).
