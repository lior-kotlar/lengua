# Lengua — planning (open work)

> **Status (2026-07-05): productionization delivered through the M4 staging leg.** Phases 0–6 are
> done; staging is live and CD-armed. What remains is the **prod cutover, live observability,
> mobile, compliance, and launch**.

This folder now tracks only **open** work. Everything **done** — phases 0–6, milestones M1–M3, the
M4 staging leg, the resolved live-staging findings, and the locked decisions & rationale — is
recorded in the repo-root **[`../CHANGELOG.md`](../CHANGELOG.md)**. The completed per-phase design
docs and phase-0–6 task files were retired after completion (git history retains them).

## Files

| File | What's in it |
| --- | --- |
| [`../CHANGELOG.md`](../CHANGELOG.md) | **What shipped** — phases 0–6, M1–M3, the M4 staging leg, resolved findings, locked decisions. |
| [outstanding-work.md](outstanding-work.md) | **What's left** — the single source of truth for open work (prod cutover, live observability, mobile, compliance, launch, backlog, tech-debt). |
| [go-live-activation.md](go-live-activation.md) | The owner-run launch runbook — a `verify:` gate on every step (§A local → §F prod → §G observability → §H host migration). |
| [owner-deferred-tasks.md](owner-deferred-tasks.md) | Owner-only repo hardening (branch protection, Dependabot) + owner setup residuals. |
| [tasks/task-tracker.md](tasks/task-tracker.md) | Forward phase rollup (7–9) + milestones. |
| [tasks/phase-7-mobile.md](tasks/phase-7-mobile.md) · [tasks/phase-8-compliance-store.md](tasks/phase-8-compliance-store.md) · [tasks/phase-9-launch.md](tasks/phase-9-launch.md) | The remaining per-phase task breakdowns (not started). |

For what's done, read **[`../CHANGELOG.md`](../CHANGELOG.md)**; for what's left, start at
**[outstanding-work.md](outstanding-work.md)**.
