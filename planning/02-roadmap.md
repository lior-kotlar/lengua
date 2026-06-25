# 02 — Roadmap (phase index)

> **The detailed, PR-sized task breakdown now lives in [`tasks/`](tasks/).** This file is the
> high-level **phase index**. For the operational view — per-phase task counts, the dependency
> graph, the critical path, and milestones — open the master rollup:
> **[`tasks/task-tracker.md`](tasks/task-tracker.md)**. For the actual checkboxes you tick as
> you work, open the per-phase file linked in the table below.

Phases are ordered by **dependency, not date**. Effort tags: **S** ≈ a day or two, **M** ≈
about a week, **L** ≈ multiple weeks (solo, part-time — adjust to your pace).

Because we launch **all platforms together**, the web app is built first (Capacitor wraps it)
and the **launch gate (Phase 9) requires web + iOS + Android ready at once**. Observability
(Phase 5) and infra/CI (Phase 6) run partly in parallel with feature work — instrument and
deploy continuously rather than at the end.

> **Quality gate applies to every phase.** From Phase 0 on, all work lands via PRs that pass
> the blocking gate in [09-testing-quality.md](09-testing-quality.md): 100% tests pass + ≥80%
> coverage (backend & frontend) + Playwright E2E. "Done" for any task includes the tests that
> keep coverage ≥80% — it is not a separate phase. Each `- [ ]` in the task files is one
> PR-sized, independently verifiable unit; promote it to a GitHub issue when you start it.

---

## Phases at a glance

| Phase | Focus (goal) | Effort | Depends on | Task file |
| ---: | --- | :---: | --- | --- |
| **0** | Repo, tooling, the per-PR CI quality gate, branch protection, shared test infra, all free-tier accounts | S–M | — | [phase-0-foundations.md](tasks/phase-0-foundations.md) |
| **1** | Domain logic behind FastAPI on Postgres (one seeded user); full Generate→Save→Review→Discover loop over HTTP | M–L | 0 | [phase-1-backend-core.md](tasks/phase-1-backend-core.md) |
| **2** | Real accounts; every row owned + isolated (proven by tests **and** RLS); export + delete | M | 1 | [phase-2-auth-multitenancy.md](tasks/phase-2-auth-multitenancy.md) |
| **3** | LLM cost guard — per-user caps, rate limits, global daily kill-switch; the key can never bill | S–M | 2 | [phase-3-llm-quota.md](tasks/phase-3-llm-quota.md) |
| **4** | React web app at full parity with Streamlit, signed in, against the API | L | 1–3 | [phase-4-web-app.md](tasks/phase-4-web-app.md) |
| **5** | Traces + logs + metrics → Grafana Cloud + Sentry; dashboards + a firing alert | S–M | 1 (starts), 3, 6 | [phase-5-observability.md](tasks/phase-5-observability.md) |
| **6** | Three environments; merge → staging auto-deploys; prod is a gated one-click promote | M | 1, 2 | [phase-6-infra-cicd.md](tasks/phase-6-infra-cicd.md) |
| **7** | Capacitor → signed iOS + Android running the full loop against prod; OTA updates | M | 4, 6 | [phase-7-mobile.md](tasks/phase-7-mobile.md) |
| **8** | Privacy/GDPR + store compliance; listings complete; closed test passes review | S–M | 7 | [phase-8-compliance-store.md](tasks/phase-8-compliance-store.md) |
| **9** | Coordinated web + iOS + Android launch + a 48-hour watch | S | 0–8 | [phase-9-launch.md](tasks/phase-9-launch.md) |

Each phase file ends with a **Phase exit gate** — capability-level checks (each with a concrete
`verify:`) that must pass before the phase counts as done.

---

## Critical path & parallelism

```
0 ─► 1 ─► 2 ─► 3 ─► 4 (web) ─► 7 (mobile) ─► 8 (compliance) ─► 9 (launch)
                     ▲
       6 (infra/CI) ─┘  runs alongside 4–6   ·   8 overlaps 7   ·   9 needs web + iOS + Android
5 (observability) starts in Phase 1 and runs alongside 1–6
```

**Critical path:** `0 → 1 → 2 → 3 → 4 → 7 → 8 → 9`.

Web (4) must precede mobile (7) because Capacitor wraps the web build. Observability (5) and
infra (6) are continuous, not a final step. The richer graph and the cross-cutting workstreams
live in [tasks/task-tracker.md](tasks/task-tracker.md).

---

## Setup readiness

A readiness check on **2026-06-25** verified ~47 account/infra items done; **6 owner items**
remain (branch protection, Dependabot, two CI secrets, a Vercel invite, Resend SMTP
confirmation, Grafana + Sentry invites) — see
[owner-setup-checklist.html](owner-setup-checklist.html). **None of these block writing code.**
Paid store accounts (Apple $99/yr, Google Play $25) are **deferred to Phase 7**. These items are
tracked as tasks in Phase 0 (`0.6`–`0.7`) and Phase 7 (`7.1`).

---

## Post-launch backlog (not blocking v1)

Offline review + sync · server push notifications (FCM/APNs) · richer product analytics ·
TTS audio for sentences · streaks/gamification · shared/importable decks · richer
import/export · i18n of the UI itself. Tracked in
[08-open-questions-and-costs.md](08-open-questions-and-costs.md).
