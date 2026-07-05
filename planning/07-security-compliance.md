# 07 — Security & Compliance

> **Status: implemented — living reference (2026-07-05).** AuthN/Z + RLS + the privacy posture shipped through Phase 2; the compliance/store items are Phase 8. Kept as the security reference.

## Authentication (Supabase Auth)

- Methods: **email/password with verification**, **Google OAuth**, **Apple OAuth**.
- Supabase issues short-lived access JWTs + refresh tokens; the client refreshes automatically.
- FastAPI verifies the JWT on every request (signature + expiry + audience), extracts the user
  UUID, and never trusts a client-supplied user id.
- Enforce a password policy + email verification before any Gemini call (also an abuse control).

## Authorization (ownership model)

- Every domain row has a `user_id`; services scope all reads/writes to `current_user`.
- **RLS in Postgres** (`user_id = auth.uid()`) as defense-in-depth, so a bug in app code can't
  leak across tenants.
- Roles are minimal for v1 (everyone is a normal user). An optional `admin` role can come later
  for support tooling.

## Secrets & key hygiene

- Server-only secrets (the LLM provider key — Groq now / Gemini later, Supabase service-role key, JWT secret, DB URL, OTLP creds)
  live in Cloud Run Secret Manager / GitHub Actions secrets — **never in the client bundle or
  git**. Only the Supabase **anon** key + public URLs ship to the client.
- Rotate keys on a schedule; document rotation in the runbook.
- Dependency scanning: **Dependabot** + `pip-audit` (Python) + `npm audit`/`pnpm audit` (web)
  in CI.

## Network & input

- HTTPS everywhere (Cloud Run + Vercel + Supabase terminate TLS).
- Strict **CORS** allowlist (web origins + the Capacitor app scheme) on the API.
- All input validated by Pydantic; size limits on words/request and payload bodies.
- Security headers on web responses (CSP, HSTS, etc.).

## Abuse & cost protection (ties to the Gemini budget)

- Email verification required before generation.
- Per-user rate limits + daily caps + the global daily kill-switch (see
  [03-backend.md](03-backend.md)).
- Consider a lightweight signup challenge (captcha) if abuse appears.
- Alert when the global budget nears the ceiling.

## Privacy & data handling

- **Disclose third parties** in the privacy policy: data stored in **Supabase**, and that the
  vocabulary/sentences a user submits are **sent to Google's Gemini API** for generation.
- Provide **data export** (JSON) and **account deletion** (hard delete with cascade) endpoints
  and surface them in-app.
- Minimize data collected; document retention; don't log raw secrets or full user content at
  info level.
- GDPR (EU audience): lawful basis, **analytics consent** (opt-in before PostHog loads), data
  **export + delete**, **EU data residency** (EU Supabase region), and a contact for requests.
  Set **SPF/DKIM** on the email domain so auth mail isn't spam-filtered.

## App store legal requirements (launch blockers)

These are **required to publish** — treat as Phase 8 gates:

- [ ] **Published privacy policy URL** (both stores require it).
- [ ] **In-app account deletion** (Apple requires it for apps with accounts; Google requires a
      deletion path **and** an external web request form).
- [ ] **Apple privacy "nutrition labels"** describing data collected/used.
- [ ] **Google Play Data Safety** form.
- [ ] **Sign in with Apple** offered on iOS **if** you offer Google (or other third-party)
      login — Apple mandates this.
- [ ] Age rating questionnaires (both stores).
- [ ] Export-compliance / encryption declaration (Apple).
- [ ] Support/contact URL.
- [ ] A reviewer demo account that exercises the full loop.

## OTA updates & store policy

The Capacitor apps use over-the-air web-bundle updates (Capgo/OSS) to ship JS/UI/CSS fixes
without a store review cycle. Keep this within store rules:

- OTA may **fix bugs and adjust the existing web UI**, not add features that change the app's
  advertised purpose or **circumvent native review** (no new native capability via OTA).
- Native/plugin changes and anything needing new permissions ship through the stores.
- **Sign/verify** update bundles and scope channels per environment (staging vs prod) so test
  bundles never reach production users.

## Pre-launch security checklist

- [ ] No secret reachable from the client bundle (audit the built web assets).
- [ ] Cross-tenant isolation proven by tests **and** RLS (try to read another user's row → denied).
- [ ] JWT verification rejects expired/forged/None-alg tokens.
- [ ] CORS rejects unknown origins.
- [ ] Rate limits + caps + global budget verified under load.
- [ ] Account deletion truly cascades (no orphan rows; Supabase auth user removed too).
- [ ] Dependency scans clean; no known criticals.
- [ ] Backups: confirm Supabase backup cadence on the free tier; export a manual snapshot
      before launch.
