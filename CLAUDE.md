# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Lengua is a personal language-learning app (Streamlit + Gemini). You enter vocabulary
words; Gemini writes natural example sentences using them; each sentence becomes two
FSRS-scheduled flashcards (recognition + production). Each language has a CEFR level that
shapes generation and adapts from review answers. See [README.md](README.md) for the full
overview.

**Status — build essentially code-complete (M1–M3 done; M4 staging leg live; prod cutover
pending — owner-gated; mobile → store → launch deferred by decision).** The app was rebuilt into a monorepo (FastAPI [`apps/api`](apps/api)
+ React [`apps/web`](apps/web) + Supabase + Cloud Run). Phases 0–6 are done: the backend core loop
(**M1**); Supabase Auth + RLS multi-tenancy + the **LLM cost guard** proven by a zero-paid-usage
load test (**M2**); the **React web app** at full parity with the legacy Streamlit app (**M3**);
observability and infra/CI-CD as-code, with the **M4 staging leg live** (auto-deploy on merge to
`main`, validated 2026-07-05). Three post-close-out hardening sweeps and the **Phase-8 compliance
code slice** (privacy policy + docs CI, public deletion path + legal routes, launch-blocker E2E,
store-listing/data-inventory) have also shipped. The domain logic lives in
[`apps/api/lengua_core/`](apps/api/lengua_core) and the original Streamlit app in
[`apps/api/legacy_streamlit/`](apps/api/legacy_streamlit) (still runnable). **What's left** is
organized into three tracks in [`planning/outstanding-work.md`](planning/outstanding-work.md):
Track 1 = code doable now (the 2026-07-11 audit follow-up items + an optional post-v1 backlog),
Track 2 = owner-gated (prod cutover, live observability, owner setup), Track 3 =
deferred by decision (mobile → store consoles → launch, after the Track-2 prod cutover). A full
completion audit ([`planning/audit-2026-07-11.md`](planning/audit-2026-07-11.md)) re-verified
every done-claim in-tree on 2026-07-11. What shipped is recorded in [`CHANGELOG.md`](CHANGELOG.md); start at
[`planning/README.md`](planning/README.md). See **Autonomous build protocol** below.

## Maintenance rules

- **Keep the README current.** Whenever a change adds or alters something significant to how
  the app is *used* — a new page or workflow, a new user-facing feature, a change to how
  review/generation behaves, a new setting or env var, or a new module worth listing in the
  project layout — update [README.md](README.md) in the same change so it always reflects
  current behavior. Purely internal refactors that don't change usage don't require a README
  edit.

## Autonomous build protocol (productionization)

Open work is executed against [`planning/outstanding-work.md`](planning/outstanding-work.md)
(single items) and [`planning/tasks/`](planning/tasks) (whole phases). To keep sessions light,
**run one item or one phase per fresh Claude Code session**:

1. A fresh session reads this file + [`planning/README.md`](planning/README.md) +
   [`outstanding-work.md`](planning/outstanding-work.md).
2. For a **single Track-1 item**: run **`/next-task`** (optionally `/next-task 1.1` or
   `/next-task #99`). For a **whole phase** (7/8/9, later): run **`/run-phase N`**. Both
   orchestrate fresh **Opus / max** agents (the
   [`phase-task-runner`](.claude/agents/phase-task-runner.md) agent) that implement → run every
   `verify:` → update the board/checkbox → open a PR → **self-merge low-risk green PRs**, or
   **pause for review** on owner/risky items (branch protection, secrets, migrations,
   security/cost-guard, architectural changes). The orchestrating session stays on the session's
   own model; implementation agents run Opus.
3. When the item/phase finishes (or hits a pause/blocker), the driver stops and reports — open a
   fresh session for the next one. Big phases (P7) may split across a couple of sessions.

**Rules every agent honors:** trunk-based (never push to `main` directly; PR + self-merge, 0
approvals); LLM = Groq `llama-3.1-8b-instant` for dev/CI, Gemini for prod, FakeLLM for E2E (zero
real LLM calls); ≥80% coverage (backend & frontend); keep the legacy Streamlit app runnable; run
every `verify:` before merging; update the README/this file when usage changes. Owner-only items
(branch-protection rule details, Dependabot, dashboard invites, paid store accounts) are surfaced
for the owner (Kotlar), not done by agents.

Tooling: [`.claude/skills/next-task/`](.claude/skills/next-task) (single items),
[`.claude/skills/run-phase/`](.claude/skills/run-phase) (whole phases),
[`.claude/agents/phase-task-runner.md`](.claude/agents/phase-task-runner.md). The plan lives at
`~/.claude/plans/you-are-implementing-phase-starry-badger.md`.
