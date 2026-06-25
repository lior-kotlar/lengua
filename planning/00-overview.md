# 00 — Overview

## Vision

Take Lengua from a **local, single-user Streamlit app** to a **deployed, multi-user product**
available as a website and as installable iOS/Android apps, with real accounts, a hosted
database, end-to-end observability, and a CI/CD pipeline — all running on free tiers.

The learning experience stays the same: type vocabulary → Gemini writes natural example
sentences → each becomes two FSRS-scheduled flashcards (recognition + production) → review
adapts your per-language CEFR level. We are changing the *delivery and operations*, not the
core idea.

## Current state (what we have today)

- **UI:** Streamlit (`app.py`, `pages/1_Generate.py`, `2_Review.py`, `3_Discover.py`,
  `4_Settings.py`, `lengua/ui.py`).
- **Core logic (framework-agnostic Python, the reusable asset):**
  - `lengua/gemini.py` — `generate_cards`, `suggest_new_words`, `explain_word` (tap-a-word)
  - `lengua/scheduler.py` — FSRS new-card state, due batch, `grade`, `is_new_card`
  - `lengua/proficiency.py` — CEFR score ↔ band, review-driven updates, manual override
  - `lengua/flashcards.py` — persist cards (recognition + production), known words, notes
  - `lengua/prompts.py` — editable rules, output format, level + suggestion instructions
  - `lengua/models.py` — `GeneratedCard`, `WordNote` (Pydantic)
  - `lengua/languages.py` — learned languages + active-language setting
  - `lengua/settings.py` — typed per-setting getters/setters (DB-backed, env fallback)
  - `lengua/config.py` — env, model name, paths, daily limits, level tuning
- **Storage:** local SQLite (`lengua/db.py`) — tables `languages`, `settings`, `cards`,
  `reviews`, `proficiency`. FSRS state stored as JSON in `cards.fsrs_state`.
- **Single user:** `DEFAULT_USER_ID = 1`; `proficiency` already carries a `user_id` column,
  but `languages` and `settings` are global, and ids are integers.

**Key insight:** the `lengua/` package is ~80% portable. The migration is mostly (1) wrap the
core in a FastAPI HTTP layer, (2) move SQLite → Postgres with a real multi-tenant schema, (3)
build a React UI to replace Streamlit, (4) operationalize it.

## Target state

- **Backend:** FastAPI service exposing the core logic as a JSON API; containerized.
- **Frontend:** one React + TypeScript app, served as a website and wrapped by Capacitor into
  native iOS + Android apps.
- **Data + Auth:** Supabase — Postgres for data, Supabase Auth for accounts (email + Google +
  Apple), Row-Level Security as defense-in-depth.
- **AI:** a **pluggable LLM provider** behind one interface, chosen by a single `LLM_PROVIDER`
  env var. **Default = Groq free tier** (e.g. `gemma2-9b-it` / a Qwen model) — *all development
  runs on Groq for now*. Switching to **Gemini** is a one-line env flip in any environment, done
  **later** to validate real prompt output and as the prod default at launch — no code change.
  The active provider's key is operator-held and gated by per-user daily caps, per-user rate
  limiting, and a project-wide daily budget kill-switch so we never exceed its free tier.
- **Ops:** 3 environments (local/staging/prod), GitHub Actions CI/CD, OpenTelemetry traces +
  logs + metrics to Grafana Cloud, Sentry error tracking, uptime checks and alerts.

## Guiding principles

1. **Reuse the core.** Don't rewrite `gemini`/`scheduler`/`proficiency`/`flashcards`; port
   them behind FastAPI and add a persistence boundary.
2. **Stay free by design.** Every dependency must have a viable free tier. LLM calls default to
   **Groq's** free tier for all development now; **Gemini** is a one-env-var switch for later /
   prod. Both run behind one provider seam and are actively capped — not hoped about.
3. **Multi-tenant from the first commit of the new backend.** Every row is owned by a user;
   never reintroduce global tables.
4. **Observable from the start.** Instrument as we build, not as an afterthought.
5. **Ship all platforms together** (per the rollout decision) — the web app is built first
   because Capacitor wraps it, but the launch gate requires web + iOS + Android.
6. **Compliance is a feature.** Account deletion, privacy policy, and data-safety disclosures
   are launch blockers for the stores, not nice-to-haves.

## Success criteria (definition of "done" for v1 launch)

- [ ] A new user can sign up (email/Google/Apple) on web, iOS, and Android and use the full
      Generate → Save → Review → Discover loop against their own private data.
- [ ] Three environments exist; merges deploy to staging automatically; prod is a gated
      promotion.
- [ ] Gemini usage cannot cause a bill: per-user caps + global daily budget guard verified.
- [ ] Traces, logs, and metrics flow to Grafana Cloud; errors flow to Sentry; an uptime
      alert fires to a real channel.
- [ ] In-app account deletion, a published privacy policy, and store data-safety forms are
      complete.
- [ ] iOS build passes TestFlight review path; Android build passes Play internal testing.

## Out of scope for v1 (candidates for later)

Offline review sync, push notifications (local reminders are in v1), TTS audio, social/shared
decks, gamification/streaks, web analytics product metrics, and billing (the architecture is
left **paid-ready** via `profiles.plan`, but no payment code ships in v1). See the backlog in
[08-open-questions-and-costs.md](08-open-questions-and-costs.md).

## Glossary

- **FSRS** — Free Spaced Repetition Scheduler; decides when each card is due.
- **CEFR** — A1→C2 proficiency scale; Lengua tracks a continuous score per language.
- **RLS** — Postgres Row-Level Security; rows are filtered by owner at the database layer.
- **Capacitor** — wraps a web app in a native shell with access to device APIs.
- **OTLP** — OpenTelemetry Protocol; the wire format for traces/logs/metrics.
- **BYOK** — bring-your-own-key (rejected for v1; we chose operator-funded + capped).
- **LLM provider** — the swappable sentence/word generator behind one interface, chosen by the
  `LLM_PROVIDER` env var. **Groq** (free tier) is the default used for all dev now; **Gemini**
  is a one-line switch for later / prod.
