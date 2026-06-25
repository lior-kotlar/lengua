<!--
Definition of Done — from planning/09-testing-quality.md.
Tick every box that applies; strike through (~~…~~) any that genuinely don't, with a one-line why.
A PR is mergeable only when the per-PR quality gate is green (100% tests pass + ≥80% backend & frontend coverage + E2E).
-->

## Summary

<!-- What does this PR change, and why? Link the task (e.g. planning/tasks/phase-N-*.md item) or issue. -->

## Definition of Done

- [ ] Tests added/updated; backend & frontend coverage stay **≥ 80%** (line + branch); all checks green.
- [ ] Behavior change? **README updated** (per the `CLAUDE.md` rule) and **OpenAPI + generated TS types regenerated**.
- [ ] New critical path is **observable** — spans/metrics/logs added (see planning/06-observability.md).
- [ ] **Security**: no secret in the client bundle; inputs validated; queries scoped to the authenticated user.
- [ ] Schema change includes a **backwards-compatible Alembic migration** (+ RLS policy).
- [ ] Quota-affecting change keeps the **LLM cost guard** intact (Groq dev/CI · Gemini prod · FakeLLM in E2E with zero real LLM calls).

## Verify

<!-- Paste the real output of every `verify:` line for the task(s) this PR closes (e.g. `python scripts/verify.py`). -->
