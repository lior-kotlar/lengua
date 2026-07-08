# Lengua — planning (open work)

> **Status (2026-07-08): all planned productionization code work is done** (two open code
> issues — #80/#95 — and the optional post-v1 backlog remain).
> Phases 0–6 are done (M1–M3 + the M4 staging leg live); three hardening sweeps and the Phase-8
> compliance code slice have shipped. What remains is organized into three tracks in
> **[outstanding-work.md](outstanding-work.md)**: **Track 1** = code doable now, **Track 2** =
> owner-gated (prod cutover, live observability, owner setup), **Track 3** = deferred by decision
> (mobile → store consoles → launch, after the Track-2 prod cutover).

This folder tracks only **open** work. Everything **done** is recorded in the repo-root
**[`../CHANGELOG.md`](../CHANGELOG.md)** (phases 0–6, milestones M1–M3, the M4 staging leg, the
resolved live-staging findings, the doable-now sweeps, the Phase-8 code slice, and the locked
decisions & rationale). Completed per-phase design docs and task files are retired after
completion (git history retains them).

## Start here

1. **What's left?** → [outstanding-work.md](outstanding-work.md) — the single source of truth,
   organized by track.
2. **Doing a Track-1 code item?** → run **`/next-task`** (spawns a fresh Opus/max
   `phase-task-runner` agent per item: implement → verify → PR → self-merge or pause).
3. **Doing a whole phase (7/8/9, later)?** → run **`/run-phase N`**.
4. **Owner going live?** → [go-live-activation.md](go-live-activation.md) (a `verify:` gate on
   every step).

## Files

| File | What's in it |
| --- | --- |
| [outstanding-work.md](outstanding-work.md) | **What's left** — the single source of truth, in three tracks (code-now / owner-gated / deferred) + tech debt. |
| [go-live-activation.md](go-live-activation.md) | The owner-run launch runbook — a `verify:` gate on every step (§A local → §F prod → §G observability → §H host migration). |
| [owner-deferred-tasks.md](owner-deferred-tasks.md) | Owner-only repo hardening (branch protection, Dependabot) + owner setup residuals. |
| [tasks/task-tracker.md](tasks/task-tracker.md) | Phase rollup (7–9) + milestones. |
| [tasks/phase-7-mobile.md](tasks/phase-7-mobile.md) · [tasks/phase-8-compliance-store.md](tasks/phase-8-compliance-store.md) · [tasks/phase-9-launch.md](tasks/phase-9-launch.md) | The remaining per-phase task breakdowns (7 and 9 not started; 8's code slice done, console half owner-blocked). |
| [`../CHANGELOG.md`](../CHANGELOG.md) | **What shipped** — the done record + locked decisions. |
