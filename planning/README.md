# Lengua — Productionization Plan

This directory is the **planning workspace** for turning Lengua from a local single-user
Streamlit app into a real, deployed, multi-user product on **web + iOS + Android**.

> Status: **planning only — no implementation yet.** These are living documents; update them
> as decisions firm up.

## Decisions locked in

| Area | Decision |
| --- | --- |
| **Backend** | FastAPI (reuses the existing Python `lengua/` core) |
| **Web frontend** | React + TypeScript (Vite) |
| **Mobile** | Capacitor — wrap the one React web app as native iOS + Android |
| **Auth + Database** | Supabase (Postgres + Auth + Row-Level Security) |
| **LLM provider** | Pluggable behind one interface, picked by `LLM_PROVIDER`. **Default = Groq free tier** — all development runs on Groq for now; flipping to **Gemini** is a one-env-var switch (later, to validate real prompts / for prod) with no code change |
| **LLM funding** | Operator-funded single key (the active provider), with strict per-user caps + rate limits + a global daily kill-switch to stay inside the free tier |
| **Rollout** | All platforms (web, iOS, Android) launch together |
| **Environments** | `local` + `staging` + `prod` (3), fit inside free tiers |
| **Observability** | OpenTelemetry → Grafana Cloud (traces, logs, metrics) + Sentry for errors |
| **Per-PR quality gate** | 100% tests pass + **≥80% coverage (backend & frontend)** + Playwright E2E green — all blocking |
| **Audience / scale** | Small public, slow growth (tens–low hundreds); operator-funded Gemini stays free via caps + kill-switch (BYOK is the growth escape hatch) |
| **Offline review** | Online-first at launch; offline is a fast-follow |
| **Audio / TTS** | Later; on-device/browser TTS first |
| **v1 feature scope** | Keep all current features (Generate, Review, Discover, Settings, multi-language, vowel marks, tap-a-word, Anki import) |
| **Monetization** | Paid-ready architecture (`plan`/tier field + metering reuse); **no billing code in v1** |
| **Accounts** | Signup required (no guest mode); seeded demo account for store reviewers |
| **Mobile updates** | OTA web-bundle live updates (Capgo/OSS) for JS/UI; native changes via the stores |
| **Auth email** | Free-tier SMTP provider (Resend/Brevo) as Supabase custom SMTP |
| **Region / privacy** | EU Supabase region; full GDPR posture (consent + export + delete) |
| **Product analytics** | PostHog (free, anonymized, consent-gated) from v1 |
| **Review reminders** | Daily on-device local notification in v1 |
| **UI stack** | React + TypeScript (Vite) with **Tailwind CSS + shadcn/ui** |
| **App identity** | Name "Lengua", id `com.lengua.app` (confirm availability) |
| **Login methods** | Email + Google + Apple (Apple required on iOS alongside Google) |
| **Language entry** | Free text — any language Gemini supports |

## The "everything free" reality

Infra, DB, auth, and observability can all be **$0** on free tiers. Three things cannot be:

- **Apple Developer Program — $99/year** (mandatory to publish to the App Store).
- **Google Play registration — $25 one-time** (mandatory to publish to Play).
- **LLM provider** — development runs entirely on **Groq's** free tier (no card required);
  **Gemini** (also free-tier) is switched on later via `LLM_PROVIDER`. The provider is the one
  cost that grows with users, so the whole quota/rate-limit design in
  [03-backend.md](03-backend.md) exists to keep it at $0.

See [08-open-questions-and-costs.md](08-open-questions-and-costs.md) for the full cost +
accounts checklist.

## Files

| File | What's in it |
| --- | --- |
| [00-overview.md](00-overview.md) | Vision, current state, target state, principles, success criteria |
| [01-architecture.md](01-architecture.md) | Target architecture, data flows, multi-tenant data model, repo layout |
| [02-roadmap.md](02-roadmap.md) | **The phased task plan (Phases 0–9) with checklists** |
| [03-backend.md](03-backend.md) | FastAPI design, Postgres schema, pluggable LLM provider (Groq/Gemini) + quota subsystem |
| [04-frontend-mobile.md](04-frontend-mobile.md) | React app + Capacitor packaging, RTL, offline, store assets |
| [05-infra-deploy.md](05-infra-deploy.md) | Hosting, 3 environments, CI/CD, secrets, free-tier limits |
| [06-observability.md](06-observability.md) | OpenTelemetry, Grafana, Sentry, dashboards, alerts, SLOs |
| [07-security-compliance.md](07-security-compliance.md) | AuthN/Z, RLS, abuse, privacy & store legal requirements |
| [08-open-questions-and-costs.md](08-open-questions-and-costs.md) | Remaining decisions, costs, accounts, and the "what else" backlog |
| [09-testing-quality.md](09-testing-quality.md) | **Test strategy + the per-PR quality gate (100% pass, 80% coverage, E2E)** |

Start with **00** for context, then **02** for the actual work breakdown.
