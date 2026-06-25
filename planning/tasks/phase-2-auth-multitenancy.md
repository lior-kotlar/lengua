# Phase 2 — Auth & multi-tenancy

> **Effort:** M  ·  **Depends on:** Phase 1 complete (FastAPI + Postgres + schema with `user_id` columns + seeded dev user)  ·  **Unlocks:** Phase 3 (LLM quota), Phase 4 (React web app)
> **Source:** roadmap Phase 2 (../02-roadmap.md) · deep dive (../07-security-compliance.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** Real accounts via Supabase Auth, with every row owned by a `user_id` and isolated so that two users can never see each other's data — proven both at the app layer (scoped queries + isolation tests) and in Postgres (RLS), plus account-lifecycle endpoints and a one-off import of the operator's historical SQLite data.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 2.1 — Supabase Auth configuration  ·  M

_Context: stand up the real identity provider (email/password + OAuth) so the backend has genuine JWTs to verify; signup is required, no guest mode._

- [ ] **2.1.1** Enable email/password auth in Supabase with email confirmation required, and configure the password policy (min length, strength) in the project Auth settings; capture the config as version-controlled `infra/supabase/config.toml` so the local CLI stack and hosted projects match.
      verify: `supabase start` then `supabase db reset` boots cleanly; a script signs up a new user via the Auth API and the returned session shows `email_confirmed_at = null` until confirmation, and `confirmation_sent_at` is set — assert in `tests/test_auth_config.py`.
- [ ] **2.1.2** Configure Google OAuth provider (client id/secret in Supabase Auth, redirect URLs for local + the eventual web/app schemes) and document the Google Cloud OAuth consent setup in `infra/supabase/oauth-setup.md`.
      verify: the Supabase Auth `/authorize?provider=google` endpoint returns a 302 redirect to `accounts.google.com` (probe with `curl -sI` against the local stack) and `infra/supabase/config.toml` lists `google` as enabled.
- [ ] **2.1.3** Configure Apple OAuth provider (Service ID, key id, team id, private key) in Supabase Auth — required on iOS because Google is offered (see 07) — and document the Apple Developer setup steps in `oauth-setup.md`.
      verify: `infra/supabase/config.toml` shows `apple` enabled with the required fields populated from env/secrets; the Supabase Auth `/authorize?provider=apple` endpoint returns a 302 to `appleid.apple.com`.
      depends: 2.1.2 (mirror the same provider-config pattern)
- [ ] **2.1.4** Set redirect/allow-list URLs and site URL for all three environments (local, staging, prod web origins + the Capacitor app scheme) in the Auth config so OAuth callbacks and email links resolve correctly.
      verify: the Auth config rejects a callback to an un-listed origin (probe returns an error) and accepts a listed one; assert the allow-list contents in `tests/test_auth_config.py`.

## 2.2 — Transactional email (custom SMTP)  ·  S

_Context: the built-in Supabase mailer is dev-only and rate-limited; wire a real SMTP provider with authenticated domains so verification/reset mail isn't spam-filtered._

- [ ] **2.2.1** Configure a custom SMTP provider (Resend or Brevo free tier) in Supabase Auth for verification, magic-link, and password-reset mail; store the SMTP credentials as secrets (never committed) and record the chosen provider in `infra/supabase/oauth-setup.md`.
      verify: Supabase Auth SMTP settings show the custom host (not the built-in sender); triggering a signup against the staging project delivers a verification email to a real inbox within ~1 min (manual check recorded in the PR) and the Auth logs show a 250 SMTP accept.
- [ ] **2.2.2** Add SPF and DKIM DNS records for the sending domain (and DMARC at `p=none` to start), per the provider's instructions, and document them in `docs/runbook.md`.
      verify: `dig TXT <domain>` shows the SPF record and `dig TXT <selector>._domainkey.<domain>` shows the DKIM key; the provider dashboard reports the domain as verified/authenticated, and a test send scores SPF=pass / DKIM=pass at a mail-tester tool (result link in the PR).
- [ ] **2.2.3** Customize the Auth email templates (confirm signup, reset password, magic link) with app branding and correct redirect links per environment.
      verify: a triggered confirmation email contains the app name and a working `{{ .ConfirmationURL }}` that points at the environment's configured site URL; assert template presence in `infra/supabase/config.toml`.

## 2.3 — Backend JWT verification → current_user  ·  M

_Context: FastAPI must verify the Supabase JWT on every request (signature + expiry + audience), extract the user UUID, and never trust a client-supplied id (see 03 `app/auth.py`, `app/deps.py`)._

- [ ] **2.3.1** Implement `app/auth.py` JWT verification using the Supabase JWT secret (HS256) and/or JWKS URL (RS256) from `pydantic-settings`, validating signature, `exp`, and `aud`; expose a typed `CurrentUser` model carrying `id` (UUID from `sub`) and `email_verified`.
      verify: `pytest tests/test_jwt.py` passes including cases that a valid Supabase-issued token yields the correct `sub`, and that signature/aud/exp are all checked (a token with a wrong audience is rejected).
- [ ] **2.3.2** Add the FastAPI `current_user` dependency in `app/deps.py` that extracts the `Authorization: Bearer` token, runs verification, and returns `CurrentUser`; return 401 on missing/invalid token. Apply it to a smoke-protected route.
      verify: `curl /me` with no token returns 401; with a valid token returns 200 and the token's user id; `pytest tests/test_deps.py` covers both.
- [ ] **2.3.3** Harden rejection of malicious tokens: expired tokens, tokens with a forged/incorrect signature, and `alg: none` ("none-alg") tokens must all be rejected with 401.
      verify: `pytest tests/test_jwt_rejection.py` asserts 401 for (a) an expired token, (b) a token re-signed with a wrong key, and (c) a hand-crafted `{"alg":"none"}` token — all three rejected.
- [ ] **2.3.4** Wire a CORS allowlist (web origins + Capacitor app scheme) and reject unknown origins, since JWT-bearing requests now come from real browsers/apps (see 07).
      verify: `pytest tests/test_cors.py` shows a preflight from a listed origin returns the `Access-Control-Allow-Origin` header and a request from an unlisted origin does not.

## 2.4 — Replace seeded user with current_user (per-user scoping)  ·  M

_Context: every repository query must be scoped to `current_user.id` instead of the Phase 1 hard-coded dev user; this is the app-layer half of tenant isolation (RLS in 2.6 is the DB half)._

- [ ] **2.4.1** Thread `current_user.id` from routers → services → repositories: add a `user_id` parameter to every repository read/write and use it in `WHERE user_id = :uid` / on insert, removing the hard-coded seeded id. Cover `languages`, `cards`, `reviews`, `proficiency`, `user_settings`.
      verify: `grep` finds no remaining hard-coded dev-user id in `app/repositories/` and `app/services/`; `pytest tests/test_repositories_scoping.py` shows each repository method filters by the passed `user_id`.
- [ ] **2.4.2** Protect all domain routers (`languages`, `generate`, `cards`, `review`, `discover`, `explain`, `proficiency`, `settings`) with the `current_user` dependency so every endpoint except `/health` requires a valid JWT.
      verify: `pytest tests/test_routes_auth.py` iterates the route table and asserts every non-`/health` route returns 401 without a token; `/health` returns 200 without a token.
- [ ] **2.4.3** Write an app-layer cross-tenant isolation test: user A creates languages/cards/reviews, then user B's token is used against list/get/grade/delete endpoints and can neither read nor mutate A's rows.
      verify: `pytest tests/test_cross_tenant_app.py` — B's `GET /languages` and `GET /review/due` never contain A's rows; B grading or deleting A's card returns 404/403 and leaves A's row unchanged.
- [ ] **2.4.4** Implement `GET /me` returning the current profile (plan) plus per-language proficiency levels for the authenticated user only.
      verify: `curl /me` with A's token returns A's languages/levels and never B's; `pytest tests/test_me.py` asserts the response is scoped to the token's user.

## 2.5 — Profiles & demo account  ·  S

_Context: a `profiles` row (PK = `auth.users.id`, `plan='free'`) must exist for every user on first login; a seeded demo/reviewer account exercises the full loop for store review; no guest mode._

- [ ] **2.5.1** Create the `profiles`-on-first-login mechanism: a Postgres trigger on `auth.users` insert (or an app-side idempotent upsert in `current_user`) that inserts a `profiles` row with `plan='free'`. Add the trigger as an Alembic migration / `infra/supabase` SQL.
      verify: `alembic upgrade head` applies; after a fresh signup, `select * from profiles where id = <new uuid>` returns exactly one row with `plan='free'`; `pytest tests/test_profiles_bootstrap.py` covers a first-login creating the row and a second login not duplicating it.
- [ ] **2.5.2** Enforce signup-required (no guest mode) end to end: there is no anonymous path that creates domain data — every write requires `current_user` (already gated by 2.4.2) and there is no anon/guest token issuance.
      verify: `pytest tests/test_no_guest.py` asserts that requests without a JWT to any write endpoint are 401 and that no code path inserts domain rows for a null/anon user.
      depends: 2.4.2
- [ ] **2.5.3** Add a seed script (`infra/supabase/seed_demo.sql` or a Python seeder) that provisions a demo/reviewer auth user (verified email, known password) with a small set of languages, generated cards (LLM-free fixtures), and at least one due card, for App Store / Play reviewers.
      verify: running the seeder then logging in as the demo user and calling `GET /review/due` returns ≥1 due card; `pytest tests/test_demo_seed.py` asserts the demo user exists, is email-verified, and has the expected seeded rows.

## 2.6 — Row-Level Security (RLS) policies  ·  M

_Context: RLS (`user_id = auth.uid()`) on every user table is defense-in-depth so an app-code bug still cannot leak across tenants (see 03 DDL + 07)._

- [ ] **2.6.1** Add an Alembic/SQL migration enabling RLS and creating owner policies (`using (user_id = auth.uid()) with check (user_id = auth.uid())`) on `languages`, `cards`, `reviews`, `proficiency`, `user_settings`; add the `profiles` self policy (`id = auth.uid()`).
      verify: `alembic upgrade head` applies; `select relname, relrowsecurity from pg_class where relname in (...)` shows `relrowsecurity = true` for every user table, and `pg_policies` lists an owner policy per table.
- [ ] **2.6.2** Ensure the backend's DB session runs under the authenticated user's identity so RLS is actually enforced (use the Supabase access token via PostgREST-style `request.jwt.claims`, or set `request.jwt.claim.sub` / `SET LOCAL role authenticated` per request) rather than connecting as a superuser that bypasses RLS.
      verify: a test that sets the per-session claim to user A then issues a raw `select * from cards` returns only A's rows even with no app-layer `WHERE`; `pytest tests/test_rls_session.py` covers it.
- [ ] **2.6.3** Write a DB-level cross-tenant isolation test (independent of app code): with the session scoped to user B, a direct `select`/`update`/`delete` against user A's `cards`/`languages`/`reviews` returns zero rows / blocks the write.
      verify: `pytest tests/test_rls.py` — under B's claim, `select` of A's rows yields 0 rows and an `update`/`delete` of A's row affects 0 rows; the same query under a superuser connection confirms A's row still exists (proving RLS blocked B, not that the row was gone).
- [ ] **2.6.4** Add a regression test asserting RLS is enabled on EVERY user table (so a future table added without RLS fails CI).
      verify: `pytest tests/test_rls_coverage.py` queries `pg_class`/`pg_policies` and fails if any table carrying a `user_id` column lacks `relrowsecurity = true` and an owner policy.

## 2.7 — Historical data migration  ·  S

_Context: a one-off script imports the operator's existing local `data/lengua.db` (SQLite) into the new prod account so historical languages/cards/reviews/proficiency aren't lost._

- [ ] **2.7.1** Write `apps/api/scripts/import_sqlite.py` that reads `data/lengua.db`, maps the old integer/global schema to the new multi-tenant Postgres schema, and inserts all rows under a single target `user_id` (the operator's account UUID, passed as an arg), preserving `fsrs_state`, `due`, `saved`, and proficiency scores.
      verify: running the script against a throwaway Postgres with the sample `data/lengua.db` and a target UUID imports without error; row counts for languages/cards/reviews/proficiency match the source counts (`pytest tests/test_import_sqlite.py` asserts equal counts and spot-checks a card's `front`/`back`/`fsrs_state`).
- [ ] **2.7.2** Make the import idempotent/safe: a `--dry-run` mode reports what would be inserted, and re-running does not duplicate rows (natural-key or import-marker guard); document the runbook step in `docs/runbook.md`.
      verify: `python scripts/import_sqlite.py --dry-run ...` writes no rows and prints the planned counts; running the real import twice yields the same final row counts (no duplicates) — asserted in `tests/test_import_sqlite.py`.
      depends: 2.7.1

## 2.8 — Account-lifecycle endpoints (export + delete)  ·  M

_Context: store compliance (Apple/Google) requires in-app data export and account deletion; deletion must hard-delete and cascade with no orphan rows, including the Supabase auth user (see 07)._

- [ ] **2.8.1** Implement `GET /account/export` returning a JSON bundle of the current user's data (profile, languages, cards, reviews, proficiency, settings) — scoped to `current_user`, nothing from other users.
      verify: `curl /account/export` with A's token returns a JSON document containing A's rows and none of B's; `pytest tests/test_account_export.py` validates the schema and the scoping.
- [ ] **2.8.2** Confirm/define `ON DELETE CASCADE` from `profiles` through `languages`/`cards`/`reviews`/`proficiency`/`user_settings`/`gemini_usage` so deleting a profile removes all dependent rows; add the migration if any FK lacks it.
      verify: `pytest tests/test_cascade.py` inserts a full graph for a user, deletes the `profiles` row, and asserts zero remaining rows in every dependent table for that `user_id` (no orphans).
- [ ] **2.8.3** Implement `DELETE /account` that hard-deletes the authenticated user: removes the `profiles` row (cascading domain data) AND deletes the Supabase `auth.users` record via the service-role Admin API, all transactional/ordered so no partial state remains.
      verify: `pytest tests/test_account_delete.py` — after `DELETE /account` for user A: A's domain rows are all gone (count 0 across tables), the `auth.users` row for A is gone, and A's old JWT is now rejected (401); user B's data is untouched.
      depends: 2.8.2
- [ ] **2.8.4** Add the cross-tenant guard on deletion/export: a user can only export/delete their own account (the endpoints take no user-id parameter; they derive it from the token).
      verify: `pytest tests/test_account_authz.py` confirms neither endpoint accepts a target-user parameter and both operate strictly on `current_user.id`; B cannot trigger deletion of A.

---

## Phase 2 exit gate

Phase 2 is DONE only when all of these hold:

- [ ] Real signup/login works for email/password (verified) + Google + Apple via Supabase Auth — verify: a new user signs up, receives a verification email through the custom SMTP domain (SPF/DKIM pass), confirms, logs in, and receives a JWT the backend accepts on `/me` (200).
- [ ] Every domain row is owned and scoped to `current_user`; no seeded/hard-coded user remains — verify: `grep` finds no hard-coded dev-user id in `app/`, and every non-`/health` route returns 401 without a token (`pytest tests/test_routes_auth.py`).
- [ ] Two users cannot see each other's data — proven at the app layer AND by RLS — verify: `pytest tests/test_cross_tenant_app.py` and `pytest tests/test_rls.py` both pass (B reads/writes of A's rows blocked at the service layer and again with a direct DB query under B's claim).
- [ ] JWT verification rejects expired, forged-signature, and `alg:none` tokens — verify: `pytest tests/test_jwt_rejection.py` passes all three rejection cases (401 each).
- [ ] A `profiles` row with `plan='free'` is created on first login and a verified demo/reviewer account exercises the full loop — verify: `pytest tests/test_profiles_bootstrap.py` and `pytest tests/test_demo_seed.py` pass (demo user logs in and `GET /review/due` returns ≥1 due card).
- [ ] Account deletion cascades with no orphan rows and removes the Supabase auth user — verify: `pytest tests/test_account_delete.py` and `tests/test_cascade.py` pass (zero rows across all dependent tables, `auth.users` row gone, old JWT rejected).
- [ ] The operator's historical `data/lengua.db` is importable into a prod account — verify: `pytest tests/test_import_sqlite.py` passes (row counts match source, idempotent re-run, dry-run writes nothing).
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E)
