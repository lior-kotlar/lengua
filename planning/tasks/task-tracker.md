# Lengua Productionization — Master Task Tracker

This is the **master index** for the Lengua productionization plan (Streamlit → FastAPI +
React + Supabase + Cloud Run, packaged to iOS/Android via Capacitor). The granular,
PR-sized tasks live in the sibling `phase-N-*.md` files in this directory; you tick the
`- [ ]` checkboxes **there**, and this file rolls them up into a single phase-level view —
a summary table, the dependency graph and critical path, the cross-cutting workstreams,
setup readiness, and the launch milestones. Start here to orient, then open the relevant
phase file to do the work.

---

## How to use this tracker

- **Work phases in dependency order.** Honor the `Depends on` column and the dependency
  graph below — a phase isn't startable until its prerequisites are met.
- **Within a phase, the groups are mostly parallel.** Each phase file is split into
  numbered groups (e.g. `1.1`, `1.2`); unless a task lists an explicit `depends:`, groups
  can progress in parallel.
- **Each `- [ ]` is one PR-sized, independently verifiable task.** Every task carries a
  `verify:` line — the concrete check that proves it's done.
- **Tick a box only when its `verify` passes** and the PR lands green under the per-PR
  quality gate (100% green + ≥80% backend & frontend coverage + Playwright E2E).
- **Optionally promote a task to a GitHub issue when you start it** (and link the PR), so
  in-flight work is visible. Update the phase Status here as a phase moves.

## Status legend

`[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Phase summary

| Phase | File | Focus | Effort | Depends on | Tasks | Status |
|------:|------|-------|:------:|------------|:-----:|--------|
| 0 | [phase-0-foundations.md](phase-0-foundations.md) | Monorepo, tooling, CI quality gate, accounts | S–M | — | 45 | in progress (0.1.x, 0.2.x, 0.3.x, 0.4.x, **0.5 CI gate (0.5.1–0.5.10)**, 0.6.1, **0.6.2**, 0.7.1–0.7.6, 0.7.11, 0.8.x done; remaining: owner items 0.6.3/0.6.4/0.7.7–0.7.10) |
| 1 | [phase-1-backend-core.md](phase-1-backend-core.md) | FastAPI + Postgres core loop, LLM seam, OpenAPI | L | 0 | 34 | not started |
| 2 | [phase-2-auth-multitenancy.md](phase-2-auth-multitenancy.md) | Supabase Auth, per-user scoping, RLS, account lifecycle | M | 1 | 28 | not started |
| 3 | [phase-3-llm-quota.md](phase-3-llm-quota.md) | LLM quota, rate-limit, cost-guard kill-switch | M | 2 | 26 | not started |
| 4 | [phase-4-web-app.md](phase-4-web-app.md) | React web app (parity with Streamlit) | L | 1–3 | 44 | not started |
| 5 | [phase-5-observability.md](phase-5-observability.md) | Tracing, logs, metrics, dashboards, alerts | S–M | 1 (starts), 3, 6 | 32 | not started |
| 6 | [phase-6-infra-cicd.md](phase-6-infra-cicd.md) | Environments, CI gate, CD pipeline, rollback | M | 1, 2 | 48 | not started |
| 7 | [phase-7-mobile.md](phase-7-mobile.md) | Capacitor → signed iOS + Android, OTA | M | 4, 6 | 50 | not started |
| 8 | [phase-8-compliance-store.md](phase-8-compliance-store.md) | Privacy/GDPR, store labels, listings, closed tests | M | 7 | 27 | not started |
| 9 | [phase-9-launch.md](phase-9-launch.md) | Coordinated web + iOS + Android launch + 48h watch | S | 0–8 | 15 | not started |

**Total: 349 PR-sized tasks across 10 phases.**

---

## Dependency graph & critical path

```
            ┌──────────────────────── cross-cutting ────────────────────────┐
            │  Observability (P5): instrument from P1 ──► finish in P5       │
            │  Infra/CI (P6): CI gate from P0 ──► deploy pipeline in P6      │
            └───────────────────────────────────────────────────────────────┘

  0 ──► 1 ──► 2 ──► 3 ──► 4 (web) ──► 7 (mobile) ──► 8 (compliance) ──► 9 (launch)
        │         │      │             ▲                  ╲                 ▲
        │         │      │             │                   ╲                │
        │         │      │             └── 6 (infra/CI) ────┘  8 overlaps 7 │
        │         │      │                  runs alongside 4–6              │
        │         │      └────────────────────────────────────────────────┐│
        │         └── 5 (observability) starts here, runs alongside 1–6 ───┘│
        │                                                                    │
        └── 9 needs web (P4) + iOS + Android (P7, via P8) all green ─────────┘
```

Edges in words:

- **0 → 1 → 2 → 3** — the backend spine (foundations, core loop, auth/multi-tenancy, cost guard).
- **4 (web)** follows **3**; **7 (mobile)** wraps the **4** web build; **8 (compliance)**
  overlaps **7**; **9 (launch)** needs **web + iOS + Android** all ready.
- **5 (observability)** *starts* in Phase 1 (auto-instrument as the backend is built) and
  runs alongside **1–6**; a couple of its tasks (infra dashboard, external uptime) land
  after the matching **6** deploy.
- **6 (infra/CI)** runs alongside **4–6** (CI gate already seeded in Phase 0).

**Critical path (explicit):**

```
0 → 1 → 2 → 3 → 4 → 7 → 8 → 9
```

---

## Cross-cutting workstreams

These run *across* phases rather than as a single block — track them continuously.

- **Observability** — instrument from **P1** (OTel auto-instrumentation + structured logs
  wired as the backend is built; custom quota spans land with **P3**), then *finish* in
  **P5** (dashboards, alerts, Sentry, external uptime). See
  [phase-5-observability.md](phase-5-observability.md).
- **Infra / CI** — the blocking **CI gate is seeded in P0** (`phase-0` group 0.5) and the
  full **deploy pipeline (CD) lands in P6** (build → Cloud Run staging → gated prod →
  rollback). See [phase-6-infra-cicd.md](phase-6-infra-cicd.md).
- **Testing & quality gate** — applies to **every PR in every phase**: 100% green + ≥80%
  backend & frontend coverage + Playwright E2E with the LLM stubbed. A task is not done
  until its tests keep coverage ≥80%. See [../09-testing-quality.md](../09-testing-quality.md).
- **Security & compliance** — threaded through **P2** (JWT/RLS/CORS, account
  export+delete), **P3** (shared-key abuse guard), **P7** (signing material as secrets,
  no leaked keys), and **P8** (privacy policy, GDPR consent/residency, store data-safety,
  deletion cascade). See [../07-security-compliance.md](../07-security-compliance.md).

---

## Setup readiness (pre-implementation)

A readiness validation on **2026-06-25** verified **~47 account/infra items done** (GitHub
repo + 28 Actions secrets, both Supabase projects, GCP `lengua-prod` + Artifact Registry +
`github-ci` SA, Vercel project, Groq/Gemini/Resend/Grafana/Sentry keys as CI secrets,
Ben's local `.env`/gcloud/Docker). Owner (Kotlar) item status (updated 2026-06-25):

1. Branch protection on `main` — **DEFERRED to launch** (non-blocking; would break the
   autonomous self-merge flow if enabled now). See [owner-deferred-tasks.md](owner-deferred-tasks.md).
2. Dependabot vulnerability alerts + automated security fixes — **DEFERRED to launch**
   (non-blocking). See [owner-deferred-tasks.md](owner-deferred-tasks.md).
3. Two CI secrets (`GCP_REGION`, `SENTRY_ORG`) — **still outstanding** (needed in Phase 5/6, not
   Phase 0).
4. Vercel access for Ben — **RESOLVED**: free-tier single manager seat; Ben is the account
   holder/manager for `lengua`. Non-blocking.
5. Resend custom-SMTP delivery confirmed in both Supabase projects — **still outstanding**
   (needed for Phase 2 auth emails).
6. Grafana Cloud + Sentry access for Ben — **DONE 2026-06-25** (Ben joined both).

So only items **3** (deploy/observability secrets) and **5** (auth email) remain truly open, and
**1–2** are deferred-by-design to launch — see [owner-deferred-tasks.md](owner-deferred-tasks.md).
**None of these block writing code.** **Paid store accounts** (Apple Developer $99/yr, Google
Play $25 one-time) are **deferred to Phase 7** and are not part of Phase 0.

---

## Milestones

| Milestone | What it proves | Lands at |
|-----------|----------------|----------|
| **M1** | Backend Generate→Save→Review→Discover loop runs over HTTP | end of **P1** |
| **M2** | Multi-user (auth + RLS) with the LLM cost guard armed | end of **P3** |
| **M3** | React web app at full parity with the legacy Streamlit app | end of **P4** |
| **M4** | Deployed to staging **and** prod (auto-staging + gated prod) | end of **P6** |
| **M5** | Signed iOS + Android builds installable on real devices | end of **P7** |
| **M6** | Coordinated web + iOS + Android launch (v1 live) | **P9** |
