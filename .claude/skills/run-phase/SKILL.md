---
name: run-phase
description: Drive an entire Lengua productionization phase (or the next incomplete one) autonomously — orchestrate fresh per-group Opus/max agents that implement, verify, and self-merge or pause for review, then stop. Use when continuing the build in a fresh session ("/run-phase", "/run-phase 1", "continue the build", "do the next phase").
---

# run-phase — autonomous phase driver

Complete one phase of the Lengua productionization plan using FRESH per-group agents (so THIS
session stays light), at high quality, then STOP so the user can open a new session for the next
phase.

## Steps

1. **Orient.** Read `CLAUDE.md`, `planning/tasks/task-tracker.md`, and the plan file. Pick the target phase:
   - If the user passed a number (`/run-phase 1`), use it.
   - Otherwise the LOWEST phase with unchecked `- [ ]` tasks (scan `planning/tasks/phase-*.md`). Finish a partially-done phase before starting the next.
2. **Plan the phase.** Read `planning/tasks/phase-N-*.md`. Build the ordered list of groups/tasks honoring every `depends:` line. Assign each a mode:
   - **auto-merge** — scaffolding / low-risk / self-verifying changes.
   - **pause** — owner-only actions (branch protection, secrets, dashboards, paid accounts), non-trivially-reversible migrations, security/auth/cost-guard, or anything you'd want a human to review. When unsure → pause.
   You decide granularity: usually one PR per group, but one-PR-per-task for big groups (e.g. `0.5` CI).
3. **Run a Workflow** (invoking this skill authorizes the Workflow tool). Drive the groups **strictly SEQUENTIALLY** — they share one git working dir, so NEVER run them in parallel. Each group via `agent(prompt, {agentType: 'phase-task-runner', model: 'opus', effort: 'max', schema: RESULT})`:
   - Give each agent a tight, self-contained prompt: the group's tasks + their exact `verify:` lines + the mode (auto-merge or pause).
   - **Abort** the run if any group returns `status: 'failed'` (return what merged + the failure_reason).
   - When a `pause` group opens its PR, **STOP the run there** and return — the human reviews/merges before continuing (later groups usually depend on it).
4. **Report** to the user: PRs merged, any PR left open for review (and why), what's blocked-on-owner, phase progress (X / total), and a one-line instruction to open a fresh session for the next step.

## RESULT schema (per agent)
`{ status: 'merged' | 'pr_open' | 'failed', pr_number?, pr_url?, checkboxes_ticked?: string[], verify_summary?, failure_reason?, summary }`

## Guardrails
- Honor the locked decisions in `CLAUDE.md`. Never push to `main` directly; agents self-merge only low-risk, green PRs.
- Owner-blocked items (e.g. Phase 0: `0.6.3` branch-protection rule details, `0.6.4` Dependabot, `0.7.8`–`0.7.10` dashboards) are NOT yours — surface them to the user.
- If the phase needs a product/architecture decision you can't confidently make, pause and ask.
- Keep THIS session light: the work lives in the sub-agents; you only orchestrate and summarize.
