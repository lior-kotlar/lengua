---
name: next-task
description: Drive ONE open work item from planning/outstanding-work.md Track 1 (or a named item/issue) end-to-end — spawn a fresh Opus/max phase-task-runner agent that implements, verifies, opens a PR, and self-merges or pauses for review. Use for single items outside a full phase ("/next-task", "/next-task 1.1", "/next-task #99", "do the next task").
---

# next-task — single-item driver

Complete ONE item from the open-work board using a FRESH agent (so THIS session stays light), at
production quality, then STOP and report. This is the single-item sibling of `/run-phase` (which
drives a whole `planning/tasks/phase-N-*.md` phase).

**Model split:** the orchestrating session (you) stays on the session's model; the implementation
agent runs **Opus 4.8 / max effort** — well-specified single items don't need the frontier model.
Reserve the session model for orchestration, ambiguous design calls, and adversarial review.

## Steps

1. **Orient.** Read `CLAUDE.md` and `planning/outstanding-work.md`. Pick the target item:
   - If the user named one (`/next-task 1.1`, `/next-task #99`), use it.
   - Otherwise the TOP item of **Track 1** (§1.1 first, then §1.2 by size — skipping #95, which
     needs an owner decision first). §1.3 backlog items are picked ONLY when the user names one;
     Track 1 counts as done when §1.1 and the eligible §1.2 items are closed. Track 2/3 items are
     owner-gated/deferred — never pick them; if the user names one, surface that it's owner-gated
     and stop.
2. **Assign the mode** before spawning:
   - **auto-merge** — low-risk, reversible, fully CI-verified (e.g. issue #99).
   - **pause** — security/auth/cost-guard code (e.g. the §1.1 limiter bound — shared with the LLM
     cost guard), migrations, architectural changes (e.g. issue #80), or anything you'd want a
     human to review. When unsure → pause.
3. **Spawn ONE `phase-task-runner` agent** (`model: 'opus'`, `effort: 'max'`) with a tight,
   self-contained prompt: the item's full spec + verify lines from the board, the mode, the
   **Rules** block, and the **environment notes** below (include both verbatim). One item per
   agent; items run sequentially (shared working tree).
4. **Report:** PR # / URL, merged or paused (and why), verify summary, and the board/CHANGELOG
   updates made. Then STOP — don't invent scope. If Track 1 is empty, say so: everything left is
   owner-gated (Track 2) or deferred (Track 3).

## Rules the agent must honor (same as /run-phase)

- Trunk-based: branch off fresh `main`, PR, self-merge only low-risk green PRs (0 approvals);
  NEVER push to `main` directly. ≥80% coverage held (backend & frontend); legacy Streamlit stays
  runnable; run every `verify:` before merging.
- **Same PR must update the paper trail:** tick/remove the item in
  `planning/outstanding-work.md`, add the CHANGELOG entry, and update README/CLAUDE.md if usage
  changed.
- LLM = Groq `llama-3.1-8b-instant` dev/CI, FakeLLM for E2E (zero real calls), Gemini prod-only.

## Environment notes (this machine — pass to the agent verbatim)

1. **Local integration/e2e are un-runnable here** — ports 4173/54322 belong to another project's
   stack, so local `pytest` runs the *offline* subset only and local Playwright can't start.
   **Rely on CI** for backend integration + FakeLLM e2e. Local gate = `ruff` / `ruff format` /
   `mypy` + `eslint` / `prettier` / `tsc` + `vitest` + offline `pytest -k "not integration"`.
2. `pnpm` is not on PATH — use `corepack pnpm …`. Run uv without `cd` via
   `uv run --directory apps/api …`. Use `python` (not `python3` — Store stub) locally.
3. **mypy must run repo-wide** (`mypy .` from `apps/api`), not file-scoped — a scoped run has
   let a test-file `arg-type` redden CI before.
4. **Regen discipline:** any API route/schema change (docstrings count — they are the OpenAPI
   operation description) requires `uv run --directory apps/api python scripts/dump_openapi.py`
   **and** `corepack pnpm --filter api-types generate`, both committed, or the lint +
   `test_openapi_stable` jobs fail.
5. **Watch for a concurrent session:** if HEAD moves unexpectedly, check `git reflog` and surface
   it before continuing.
6. Never sweep-edit files via PowerShell (mangles UTF-8); use the Edit/Write tools.
