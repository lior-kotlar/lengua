# Branch protection & required status checks

This documents the branch-protection policy for `main` and the **exact** required status-check
names so the configuration is committed, not tribal. It mirrors the per-PR quality gate defined
as-code in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

> **Owner action (Kotlar).** Enabling protection on `main` is task **0.6.3** and is intentionally
> deferred to just before launch — turning it on now would block the autonomous self-merge flow
> (which relies on 0 required approvals). This file is the spec to apply when that switch is
> flipped. See [`planning/owner-deferred-tasks.md`](../planning/owner-deferred-tasks.md).

## Policy for `main`

| Setting | Value | Why |
| --- | --- | --- |
| Require a pull request before merging | **on** | Trunk-based; never push to `main` directly. |
| Required approving reviews | **1** | One approving review (self-review is fine while solo). |
| Dismiss stale approvals on new commits | **on** | A new push invalidates prior approval — re-review the final diff. |
| Require status checks to pass | **on** | The gate below must be green to merge. |
| Require branches to be up to date before merging | **on** (strict) | The PR must be rebased on the latest `main` so checks run against what actually merges. |
| Require conversation resolution | **on** | No unresolved review threads at merge. |
| Require linear history (squash-only) | **on** | Squash-merge with a Conventional-Commits title for a clean changelog. |
| Include administrators | **on** | The rules apply to everyone, including the owner. |
| Allow force pushes / deletions | **off** | Protect `main` history. |

> While the autonomous build is running, `required_approving_review_count` is **0** (solo
> self-merge). Raise it to **1** at launch (0.6.3). The required-status-checks list below applies
> in both modes.

## Required status checks (exact names)

These are the GitHub **check names** as they appear on a PR — they equal each job's `name:` in
`.github/workflows/ci.yml`. All of the following must be **green** for a PR to be mergeable:

| Required check (exact) | Job id in `ci.yml` | Gate it enforces |
| --- | --- | --- |
| `lint + format + types` | `lint-and-types` | ruff check + ruff format --check + mypy (api); eslint + prettier --check + tsc --noEmit (web). |
| `backend tests + coverage` | `backend-tests` | `pytest --cov --cov-branch --cov-fail-under=80` against the Supabase-CLI test Postgres. |
| `frontend tests + coverage` | `frontend-tests` | `vitest run --coverage` with v8 80% line/branch/function/statement thresholds. |
| `build (api image + web bundle)` | `build` | Builds the API Docker image (multi-stage uv) + the web Vite bundle as artifacts. |
| `e2e (ephemeral stack, FakeLLM)` | `e2e` | Ephemeral stack (web bundle + API container with `LLM_PROVIDER=fake`, no Groq/Gemini keys + disposable seeded Postgres); Playwright home-page smoke + asserts the LLM seam is exercised with **zero real LLM calls**. |
| `security (audit + secrets)` | `security` | pip-audit (api) + pnpm audit (web) + gitleaks secret scan. |

When configuring protection, add each name in the **Required checks** field exactly as written in
the first column (copy/paste — names contain spaces, parentheses, and commas).

> The `setup (warm caches)` job is a dependency that fans out to the checks above; it does not
> need to be listed separately (a failure there fails its dependents). Listing the six leaf checks
> is sufficient and is what this policy requires.

### Advisory (NOT required — never block merge)

These run on every PR for visibility but are intentionally **excluded** from the required list:

| Check | Job id | Why advisory |
| --- | --- | --- |
| `a11y + perf (advisory)` | `a11y-perf` | axe + Lighthouse CI budgets — advisory until budgets are tuned (`continue-on-error: true`). |
| `coverage delta (PR comment)` | `coverage-comment` | Posts a backend + frontend coverage comment; informational only. |

Do **not** add the advisory checks to required status checks — doing so would make a tuning/comment
job gate merges, which contradicts the deliberate "start advisory" decision.

## Applying the policy (owner, at launch)

With the `gh` CLI (run by the owner; requires admin on the repo):

```bash
gh api -X PUT repos/lior-kotlar/lengua/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[checks][][context]=lint + format + types' \
  -f 'required_status_checks[checks][][context]=backend tests + coverage' \
  -f 'required_status_checks[checks][][context]=frontend tests + coverage' \
  -f 'required_status_checks[checks][][context]=build (api image + web bundle)' \
  -f 'required_status_checks[checks][][context]=e2e (ephemeral stack, FakeLLM)' \
  -f 'required_status_checks[checks][][context]=security (audit + secrets)' \
  -F 'enforce_admins=true' \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
  -F 'required_linear_history=true' \
  -F 'required_conversation_resolution=true' \
  -F 'allow_force_pushes=false' \
  -F 'allow_deletions=false' \
  -F 'restrictions=null'
```

Verify it took (task 0.6.3):

```bash
gh api repos/lior-kotlar/lengua/branches/main/protection \
  --jq '.required_pull_request_reviews.required_approving_review_count, [.required_status_checks.checks[].context]'
```
