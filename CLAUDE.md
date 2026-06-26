# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Lengua is a personal language-learning app (Streamlit + Gemini). You enter vocabulary
words; Gemini writes natural example sentences using them; each sentence becomes two
FSRS-scheduled flashcards (recognition + production). Each language has a CEFR level that
shapes generation and adapts from review answers. See [README.md](README.md) for the full
overview.

**Status — productionization in progress (Phase 3 complete → M2 reached).** The app is being
rebuilt into a monorepo (FastAPI [`apps/api`](apps/api) + React [`apps/web`](apps/web) + Supabase +
Cloud Run). Phases 0–3 are done: the backend core loop (M1), Supabase Auth + RLS multi-tenancy, and
the **LLM cost guard** (per-user daily caps + rate limits + a global daily kill-switch + concurrency
cap + observability spans/metrics) — proven by a zero-paid-usage load test — so **M2 (multi-user
with the cost guard armed)** is reached. The domain logic now lives in
[`apps/api/lengua_core/`](apps/api/lengua_core) and the original Streamlit app in
[`apps/api/legacy_streamlit/`](apps/api/legacy_streamlit) (still runnable). Plan + tasks:
[`planning/`](planning) and [`planning/tasks/task-tracker.md`](planning/tasks/task-tracker.md).
See **Autonomous build protocol** below.

## Maintenance rules

- **Keep the README current.** Whenever a change adds or alters something significant to how
  the app is *used* — a new page or workflow, a new user-facing feature, a change to how
  review/generation behaves, a new setting or env var, or a new module worth listing in the
  project layout — update [README.md](README.md) in the same change so it always reflects
  current behavior. Purely internal refactors that don't change usage don't require a README
  edit.

## Autonomous build protocol (productionization)

The productionization is executed task-by-task against [`planning/tasks/`](planning/tasks). To
keep sessions light, **run one phase per fresh Claude Code session**:

1. A fresh session reads this file + [`task-tracker.md`](planning/tasks/task-tracker.md).
2. Run **`/run-phase`** (optionally `/run-phase N`). It orchestrates fresh per-group **Opus / max**
   agents (the [`phase-task-runner`](.claude/agents/phase-task-runner.md) agent) that
   implement → run every `verify:` → tick the checkbox → open a PR → **self-merge low-risk green
   PRs**, or **pause for review** on owner/risky items (branch protection, secrets, migrations,
   security/cost-guard, architectural changes).
3. When the phase finishes (or hits a pause/blocker), the driver stops and reports — open a fresh
   session for the next phase. Big phases (P1, P4, P6) may split across a couple of sessions.

**Rules every agent honors:** trunk-based (never push to `main` directly; PR + self-merge, 0
approvals); LLM = Groq `llama-3.1-8b-instant` for dev/CI, Gemini for prod, FakeLLM for E2E (zero
real LLM calls); ≥80% coverage (backend & frontend); keep the legacy Streamlit app runnable; run
every `verify:` before merging; update the README/this file when usage changes. Owner-only items
(branch-protection rule details, Dependabot, dashboard invites, paid store accounts) are surfaced
for the owner (Kotlar), not done by agents.

Tooling: [`.claude/skills/run-phase/`](.claude/skills/run-phase),
[`.claude/agents/phase-task-runner.md`](.claude/agents/phase-task-runner.md). The plan lives at
`~/.claude/plans/you-are-implementing-phase-starry-badger.md`.
