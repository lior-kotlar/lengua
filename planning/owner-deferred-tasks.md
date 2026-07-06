# Owner-deferred tasks (Kotlar) — do at the very end, before launch

These are **owner-only repo-hardening actions** that need GitHub **admin** rights on
`lior-kotlar/lengua` and are **intentionally deferred to the end of the build** (at / just
before the Phase 9 launch). **None of them block any implementation work.** They harden the
trunk and the supply chain *after* the quality gate and deploy pipeline are proven — and turning
branch protection on early would actually break the autonomous PR + self-merge flow the build
relies on (it self-merges low-risk green PRs with 0 approvals).

> **Owner:** Lior Kotlar (repo admin). Ben (`benartzi4@gmail.com`) cannot do these without admin.
> **Status:** deferred — *non-blocking*. When done, tick the matching boxes in
> this file (`0.6.3` branch protection, `0.6.4` Dependabot) — the phase-0 task file was retired post-completion (see [`../CHANGELOG.md`](../CHANGELOG.md)).

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

## Other open owner items (tracked in `outstanding-work.md`)

The remaining owner residuals live in [`outstanding-work.md`](outstanding-work.md) §(F); listed
here only so this file gives one owner view alongside the two end-of-build hardening actions above:

- **Resend custom SMTP + SPF/DKIM/DMARC** on a verified domain → re-enable prod email confirmation
  (issue #103); staging runs the interim `mailer_autoconfirm=true`, which must NOT ship to prod.
- **Google + Apple OAuth** creds + `VITE_OAUTH_PROVIDERS` per env (Apple needs a paid account; the
  merged default is Google-only, so the Apple button is hidden today).
- **Gate prod `/docs` `/redoc` `/openapi.json`** before public launch (accepted on staging).

Completed owner items — `0.7.7` (CI secrets `GCP_REGION`/`SENTRY_ORG`), `0.7.9` (Vercel access),
`0.7.10` (Grafana/Sentry onboarding), and the resolved live-staging findings **S1–S22** (incl.
#91 erasure-cascade, #83 security-headers/CORS, #71 stable Vercel alias) — are recorded in
[`../CHANGELOG.md`](../CHANGELOG.md).
