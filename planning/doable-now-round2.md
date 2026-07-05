# Doable-now follow-ups — round 2 (no prod, no mobile)

**What this is:** the work order for the next fresh session. Round 1 (2026-07-05, PRs #117–#124 —
API hardening, web tap-a-word a11y, docs-sync + broken-reference cleanup, web perf/code-splitting,
Apple polish + prompts/use-toast coverage, RLS-migration SQL-parse) is **done** (see
[`../CHANGELOG.md`](../CHANGELOG.md)); `main` is clean, zero open PRs. This doc lists the remaining
**doable-now** work: the CI-only test debt intentionally split out of round 1, the a11y-CI
broadening, code-comment hygiene, and a couple of one-offs. Everything left after this is
owner/prod/mobile.

Single source of truth for what's left overall: [`outstanding-work.md`](outstanding-work.md).

---

## Guardrails (every PR)

- **Trunk-based:** branch off `main` → PR → **self-merge when green** (`gh pr merge <n> --squash
  --delete-branch`, then move on). 0 approvals; branch protection is intentionally off.
- **CI is the verify.** Run the local verify where you can, but two of these tests are
  `@pytest.mark.integration` and only run in CI (they need the Supabase test Postgres + auth).
- **Do NOT touch:** prod, mobile/Capacitor, `deploy-*.yml`, secrets, or migrations — *including
  comments inside already-applied migration files*.
- **One `apps/web` PR at a time:** merge each web PR to green **before** opening the next web PR
  (this is what closed #118 to a merge-race). PRs that touch only `apps/api` don't race the web ones.
- Local verify commands: web → `corepack pnpm --filter web run verify` (eslint + prettier + tsc +
  vitest --coverage + build; needs `dist/`+`coverage/` which are gitignored, so `git add -A` is
  safe). api → `cd apps/api && uv run ruff check … && uv run mypy … && uv run pytest …`.
  ⚠ Local FakeLLM e2e needs ports **4173 + 54322** free; the user's "Sound Clash" project holds
  them — don't stop it, **rely on CI's e2e job** for anything e2e.
- Keep `CHANGELOG.md` + `outstanding-work.md` in step as items close (see "When the sweep is done").

Suggested order: **PR-G → PR-H → PR-I**, then the one-offs.

---

## PR-G — Account-lifecycle integration tests (`apps/api`, CI-only)

The two tests deferred from #123 (tracked as "Test nits (account-lifecycle, CI-only)" in
`outstanding-work.md`). Both are `@pytest.mark.integration` → they auto-skip locally without a DB and
run against the CI Postgres. **Validate locally with `ruff` + `mypy` + `pytest … --collect-only`**
(catches import/fixture/syntax errors), then let CI run them. Mirror the existing passing tests
exactly — don't invent fixtures.

### G1 — export-under-real-RLS → add to `tests/test_account_export.py`
- **Gap:** `test_export_is_scoped_to_the_token_user` proves the *app-layer* `WHERE user_id` filter,
  but runs through the `multiuser_client` fixture whose `get_db` is a **superuser** session that
  *bypasses RLS*. Nothing proves the export succeeds and stays scoped under the real `authenticated`
  role with Postgres RLS enforcing.
- **Add:** a test that drives `GET /account/export` through the **un-overridden scoped `get_db`**
  (authenticated role, RLS on). **Mirror the pattern in
  `tests/test_rls_session.py::test_real_get_db_scopes_an_http_request_end_to_end`** (it shows exactly
  how to swap in the real async session + install the caller's JWT identity). Seed a committed second
  user **B** via privileged psycopg (reuse `tests/rls_helpers.py::seed_user`), then assert A's export
  is `200`, `profile.id == A`, and **none** of B's rows/text (`B-French`, B's id) appear — proving
  RLS, not just the app filter, scopes it.
- **Helpers/imports:** `tests/rls_helpers.py` (`seed_user`, `RLS_USER_TABLES`), `tests/auth_helpers.py`
  (`authenticate_as` / `auth_header`), `app.db.session` (`get_db`, `async_dsn`), `app.main.create_app`,
  `app.deps.get_llm_provider`, `app.schemas.account.AccountExport`, `lengua_core.llm.fake.FakeLLM`,
  and `tests/conftest.py`'s DB-skip guard.

### G2 — deleted-but-unexpired-token → add to `tests/test_account_delete.py`
- **Gap:** existing tests check GoTrue's *session* rejection and the idempotent second `DELETE`, but
  nothing tests what one of the **app's own read endpoints** returns for a deleted account's
  still-valid (within-`exp`) JWT. The app verifies tokens statelessly via JWKS, so the token still
  verifies until it expires.
- **Add:** create user A (+ a live neighbour B), seed both, login A, `DELETE /account` (→ 204). Then
  with the **same** still-valid JWT, `GET /account/export` → assert it still verifies (not 401) and
  returns `200` with an **empty** bundle (`profile is None`, all lists `[]`, `settings == {}`), never
  B's data, never 500.
- **Reuse the helpers already in this file:** `_seed_committed_graph` (~L194), `_real_stack_settings`
  (~L247), and `tests.supabase_auth` (`create_confirmed_user`, `login`, `delete_user`). Copy the
  fixture wiring from `test_delete_account_twice_is_idempotent_over_http` (~L348).
- **⚠ Design-contract check first:** this asserts the *current* behavior (200 + empty bundle). If the
  team wants a hard **401** for deleted-but-unexpired tokens instead, that needs a stateful revocation
  check the stateless JWKS path doesn't do — confirm the intended contract before writing the
  assertion; default to the 200-empty the code produces today.

**On landing both:** delete the "Test nits (account-lifecycle, CI-only)" bullet from
`outstanding-work.md`.

**Verify:** `uv run ruff check tests/test_account_export.py tests/test_account_delete.py` + `uv run
mypy …` + `uv run pytest tests/test_account_export.py tests/test_account_delete.py --collect-only`;
CI's "backend tests + coverage" runs them for real.

---

## PR-H — Broaden the advisory a11y CI past `/login` (`ci.yml` + e2e)

- **Today:** the `a11y-perf` job (`.github/workflows/ci.yml` ~L552, **advisory / non-blocking**) runs
  Lighthouse CI + `npx @axe-core/cli@4 http://127.0.0.1:4173 --exit` — i.e. axe on the **login page
  only**. `@axe-core/playwright` is **not** a dependency yet (only `@playwright/test`).
- **Do:** add `@axe-core/playwright` (+ `axe-core`) as a web devDependency and write a Playwright a11y
  spec (e.g. `apps/web/e2e/a11y.spec.ts`) that runs under the **FakeLLM e2e harness** the `e2e` job
  already stands up (web bundle + API container with `LLM_PROVIDER=fake`, no real keys + a seeded
  Postgres). It should log in as the seeded demo user (see how `apps/web/e2e/*.spec.ts` already
  authenticate) and run `new AxeBuilder({ page }).analyze()` on the authenticated surfaces —
  dashboard, generate, review, discover, settings — reporting violations **without failing the build**
  (advisory: `console.warn` / attach results / a `continue-on-error` step). Keep it advisory; never a
  merge gate.
- **Wire it** into the `a11y-perf` (or `e2e`) job as an advisory step. Confirm the harness's login
  flow + demo credentials from the existing e2e specs before writing it.
- **Verify:** the job runs green (advisory never blocks). Locally the FakeLLM e2e needs ports
  4173 + 54322 (held by "Sound Clash") — rely on CI. On landing, update the "Advisory a11y CI covers
  only `/login`" bullet in `outstanding-work.md`.

---

## PR-I — Code-comment doc-citation hygiene (repoint deleted-planning-doc refs)

Round 1 (#116) deleted the numbered `planning/0X-*.md` design docs; a few **code comments/docstrings**
still cite them (noted as "Stale code-comment doc citations" in `outstanding-work.md`). Repoint each to
`CHANGELOG.md` / `ci.yml` (or drop the citation), keeping the surrounding descriptive text. Comment-only,
no behavior change.

- `apps/api/app/quota.py` — `03-backend.md` (×3: ~L4, L333, L551)
- `apps/api/app/repositories/__init__.py` — `03-backend.md` (~L5)
- `apps/api/lengua_core/llm/keys.py` — `08-open-questions-and-costs.md` (~L17)
- `.github/workflows/ci.yml` — `09-testing-quality.md` (~L3 comment)
- `apps/web/e2e-staging/signup.spec.ts` — `staging-validation/VALIDATION-REPORT.md` (~L12)
- **SKIP** `apps/api/migrations/versions/20260630_0006_*.py` — migrations are off-limits even for
  comments; leave it (already accepted in `outstanding-work.md`).

**Verify:** `ruff` + `mypy` (api) + `eslint` (web) + the touched suites still pass. On landing, trim the
"Stale code-comment doc citations" bullet in `outstanding-work.md` to just the migration comment.

---

## One-offs (not PRs)

- **Prune merged remote branches.** ~34 stale `origin/*` branches remain, all confirmed **merged**
  (squash) PR branches — safe residue. Optional cleanup: confirm it's wanted, then delete the
  merged set (cross-check each against `gh pr list --state merged --head <branch>` before
  `git push origin --delete <branch>`). Keep `main`/`HEAD`. Not required; skip if the owner prefers to
  keep them.
- **Design QA of round-1 polish.** Run the app on the FakeLLM harness and eyeball two round-1 changes:
  (1) the #122 tap-a-word popover (`w-64` → `max-w-xs` makes it **content-hug**, so verify short /
  loading / error states aren't awkwardly narrow in **both LTR and RTL**), and (2) the type-scale
  sweep, against the spec at `~/.claude/plans/lengua-apple-redesign-spec.md`. Fix any regression as a
  small className-only PR.

---

## OUT of scope here (do NOT start these)

- **Prod cutover, live observability dashboards, mobile** — owner/prod
  ([`go-live-activation.md`](go-live-activation.md) §F/§G; `tasks/phase-7/8/9`).
- **Observability as-code follow-ups that only light up with live infra** (`proficiency_cefr_band`
  metric, browser client span → Tempo, web-Sentry ↔ Tempo unify by `trace_id`) — leave for Phase 5
  (owner); low value without the deployed stack.
- **Owner setup** (branch protection, Dependabot incl. the Docker base-image digest, Resend SMTP,
  Google/Apple OAuth) — [`owner-deferred-tasks.md`](owner-deferred-tasks.md).

---

## When the sweep is done

- Add the PRs to the "Post-close-out" section of [`../CHANGELOG.md`](../CHANGELOG.md) and remove the
  closed items from [`outstanding-work.md`](outstanding-work.md).
- Delete this file (it's a one-shot work order; git history keeps it) if all of PR-G/H/I land.
- Report what merged + the final remaining list (which should then be only owner/prod/mobile).
