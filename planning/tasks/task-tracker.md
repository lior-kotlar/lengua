# Task tracker — forward work (phases 7–9)

Phases 0–6 are **done** (M1–M3 + the M4 staging leg) — the shipped work, PR refs, and locked
decisions live in [`../../CHANGELOG.md`](../../CHANGELOG.md). This tracker covers only the
**remaining** phases; the single list of open work (in three tracks: code-now / owner-gated /
deferred) is [`../outstanding-work.md`](../outstanding-work.md), and the owner launch runbook is
[`../go-live-activation.md`](../go-live-activation.md). Single Track-1 code items run via
**`/next-task`**; whole phases via **`/run-phase N`**.

**Status legend:** ✅ done · ◐ as-code done / live-owner-deferred · ☐ not started

## Phase summary

| Phase | Focus | Status |
|------:|-------|--------|
| 0–4 | Monorepo/CI · core loop **M1** · auth+RLS+account · cost guard **M2** · React web **M3** | ✅ DONE — see CHANGELOG (owner OAuth/SMTP residual in outstanding-work Track 2) |
| 5 | Tracing, logs, metrics, dashboards, alerts | ◐ as-code DONE; live dashboards owner-deferred ([go-live §G](../go-live-activation.md)) |
| 6 | Environments, CI gate, CD pipeline, rollback | ◐ as-code DONE; **M4 staging leg live**; prod cutover owner ([go-live §F](../go-live-activation.md)) |
| 7 | [phase-7-mobile.md](phase-7-mobile.md) — Capacitor → signed iOS + Android, OTA | ☐ not started (deferred by decision) |
| 8 | [phase-8-compliance-store.md](phase-8-compliance-store.md) — privacy/GDPR, store, data-safety | ◐ **code slice DONE** (#130–#133: privacy policy + docs CI, public deletion path + legal routes, launch-blocker E2E, store-listing/data-inventory/residency); store-console half owner-blocked on paid accounts + prod |
| 9 | [phase-9-launch.md](phase-9-launch.md) — coordinated web + iOS + Android launch + 48h watch | ☐ not started (deferred by decision) |

## Milestones

| Milestone | What it proves | Status |
|-----------|----------------|--------|
| **M1** | Backend Generate→Save→Review→Discover loop over HTTP | ✅ done (P1) |
| **M2** | Multi-user (auth + RLS) with the LLM cost guard armed | ✅ done (P3) |
| **M3** | React web app at full parity with the legacy Streamlit app | ✅ done (P4) |
| **M4** | Deployed to staging **and** prod (auto-staging + gated prod) | 🟡 **staging leg LIVE & validated 2026-07-05**; prod leg = owner cutover ([go-live §F](../go-live-activation.md)) |
| **M5** | Signed iOS + Android builds installable on real devices | ☐ end of P7 |
| **M6** | Coordinated web + iOS + Android launch (v1 live) | ☐ P9 |

## Forward critical path

**Track-1 code items** (`/next-task` — the required limiter-bound hardening item is now done (#141);
what's left is the open code issues + the optional post-v1 backlog) run any time. Then, in order:
**M4 prod cutover** (owner — go-live §F) → **P7 mobile** (Capacitor, signed
builds, store accounts) → **P8 store-console half** (labels, data-safety, listings, closed tests) →
**P9 launch** (cross-platform smoke, store submit/promote, 48h watch). P5 live observability
(owner — go-live §G) runs alongside and closes with the prod cutover.
