# 05 — Infrastructure, Environments & CI/CD

## Hosting choices (all free-tier)

| Layer | Choice | Free-tier notes |
| --- | --- | --- |
| **Backend (FastAPI)** | **Google Cloud Run** | Scales to zero, generous monthly free requests, ~1–2s cold start, no forced sleep. Containerized. |
| **Web frontend** | **Vercel** | Free Hobby tier for static React; preview deploys per PR. (Netlify / Cloudflare Pages are equivalent fallbacks.) |
| **DB + Auth** | **Supabase** | Free project: Postgres + Auth + RLS + storage. |
| **Redis (if needed for rate limits)** | **Upstash** | Free tier; or skip Redis and use Postgres counters. |
| **CI/CD** | **GitHub Actions** | Free minutes for the project's scale. |
| **Telemetry** | **Grafana Cloud** + **Sentry** | Free tiers; see [06-observability.md](06-observability.md). |

### Why Cloud Run over Render/Fly for the backend
Render's free web services **sleep after ~15 min** of inactivity with a slow wake — bad for a
mobile app's first request of the day. Cloud Run scales to zero but wakes fast and has a large
free request allowance. Fly.io is a fine alternative (small always-on allowance). Pick Cloud
Run unless you hit a snag.

## Environments

Three environments, kept inside free limits:

| Env | Web | API | DB + Auth | Notes |
| --- | --- | --- | --- | --- |
| **local** | Vite dev server | uvicorn (reload) | **Supabase CLI** (Docker) | Free, unlimited; doesn't consume a hosted project slot. |
| **staging** | Vercel (preview/staging) | Cloud Run `lengua-api-staging` | Supabase hosted project #1 | QA + store **test** builds point here. |
| **prod** | Vercel (production) | Cloud Run `lengua-api-prod` | Supabase hosted project #2 | Live users; store **release** builds point here. |

> **Free-tier constraint to respect:** a Supabase free org limits the number of *active*
> hosted projects (commonly 2). Using the **local CLI stack** for dev keeps staging + prod
> within that limit. If you'd rather have only 2 environments, drop staging and use Vercel
> preview deploys + local as your pre-prod. Confirm current Supabase limits when you set up.

Each env gets its own Supabase keys, **LLM provider config** (`LLM_PROVIDER` + key + model —
**default Groq in every env for now**; flip an env to Gemini later with no code change), quota
ceilings, OTLP credentials, and API base URL.

## Secrets management

Never in git. Per platform:

- **Cloud Run**: mount secrets from Secret Manager (`LLM_PROVIDER`, `GROQ_API_KEY` (set now),
  `GEMINI_API_KEY` (add later when flipping to Gemini), `DATABASE_URL`, `SUPABASE_JWT_SECRET`,
  `OTEL_*`, `SENTRY_DSN`, quota ceilings).
- **Vercel**: project env vars per environment (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`,
  `VITE_API_BASE_URL`, web `SENTRY_DSN`). Only the **anon** key and public URLs go to the
  client — never the service-role key or any LLM provider key (Groq/Gemini).
- **GitHub Actions**: repo/environment secrets for deploy credentials (GCP service account,
  Vercel token, Supabase access token) + mobile signing material.
- **Mobile signing**: iOS certs/provisioning profile + Android keystore stored as encrypted CI
  secrets (or via Fastlane match).

## Transactional email & data region

- **Custom SMTP**: configure a free-tier provider (e.g. **Resend** or **Brevo**) as Supabase's
  SMTP for verification/reset emails — the built-in sender is rate-limited and dev-only. Set
  **SPF/DKIM** on the sending domain for deliverability; store the SMTP key as a per-env secret.
- **EU region**: create the staging + prod Supabase projects in an **EU region** (data
  residency for a mostly-EU audience), and prefer EU regions for Cloud Run + Vercel too to keep
  latency and data flow consistent.

## CI/CD pipelines (GitHub Actions)

> The per-PR gate is defined in full in [09-testing-quality.md](09-testing-quality.md). It is
> **blocking** and enforced by branch protection on `main`: 100% tests pass + ≥80% coverage
> (backend & frontend) + Playwright E2E + lint/types/build/security/a11y.

```
PR opened/updated  (all required, blocking — see 09)
  ├─ lint + format + typecheck   (ruff/eslint, prettier, mypy/tsc)
  ├─ api:  pytest --cov  (fail < 80%)   unit + integration (Postgres)
  ├─ web:  vitest --coverage  (fail < 80%) + build
  ├─ contract: OpenAPI ↔ generated TS client drift
  ├─ E2E:  Playwright on ephemeral stack, Gemini stubbed
  └─ security: pip-audit + pnpm audit + gitleaks

merge to main
  ├─ build & push API image → deploy Cloud Run (staging)
  ├─ run Alembic migrations against staging DB
  └─ deploy web → Vercel (staging)

release tag (or manual "promote" approval)
  ├─ deploy API image → Cloud Run (prod)
  ├─ run Alembic migrations against prod DB (gated)
  ├─ deploy web → Vercel (prod)
  ├─ (Phase 7+) build signed iOS/Android via Fastlane → TestFlight / Play track
  └─ (Phase 7+) push web-layer OTA update to the prod channel (Capgo/OSS)
```

Guardrails: migrations run as a discrete, logged step; prod is gated by an approval; keep the
previous Cloud Run revision for one-click rollback.

### Release safety: feature flags

Because all three platforms launch together (and mobile fixes otherwise wait on store review),
gate risky/new features behind simple **feature flags** (env-driven or a small flags table).
This lets you merge code dark, enable it per environment, and disable a misbehaving feature in
prod **without a redeploy or a store update** — the safest way to ship a coordinated launch.

## Database migrations & seeding

- **Alembic** is the single source of truth for schema; apply it to local → staging → prod in
  order via CI.
- RLS policies + Supabase-specific SQL live in `infra/supabase/` and are applied via the
  Supabase CLI alongside Alembic.
- Seed scripts: a demo/reviewer account (for store review) and local dev fixtures.
- The one-off **import of your existing `data/lengua.db`** runs against prod after your account
  exists (Phase 2 task).

## Domains (optional, mostly free)

- Use free subdomains to start: `*.vercel.app` (web) and the Cloud Run URL (API).
- If you want a custom domain later (~$10/yr, the only optional cost): web apex/`www` on
  Vercel, `api.` on Cloud Run; set CORS + Supabase redirect URLs accordingly.

## Runbook (document in `docs/runbook.md`)

Deploy, rollback, rotate a secret, run a migration, respond to a budget-exhausted alert,
restore from backup, and the store-release checklist.

## Free-tier limits to track (verify current numbers at setup)

| Service | Watch |
| --- | --- |
| Supabase | active project count, DB size, monthly active users, pausing of idle projects |
| Cloud Run | monthly requests / CPU-seconds, max instances |
| Vercel | bandwidth, build minutes |
| LLM provider (Groq now / Gemini later) | RPM / requests-per-day / tokens-per-minute, per active provider (drives the global budget ceiling) |
| Grafana Cloud | series / logs GB / traces GB retention |
| GitHub Actions | monthly minutes |

Set the **global budget ceiling** from the active provider's real, current numbers (Groq now;
re-set it from Gemini's numbers when you switch) — it is the backstop that keeps the bill at $0.
