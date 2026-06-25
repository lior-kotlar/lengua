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

## Resolved owner items (for the record)

- **`0.7.9` Vercel access — RESOLVED (2026-06-25).** On the **free** tier a project has a single
  manager seat; Ben (`benartzi4@gmail.com`) is the account holder/manager for `lengua`. Not
  blocking — proceeding as-is.
- **`0.7.10` Grafana Cloud + Sentry — DONE (2026-06-25).** Ben joined Grafana Cloud and both
  Sentry projects (lengua-api, lengua-web).
