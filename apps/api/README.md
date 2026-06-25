# apps/api — Lengua API (FastAPI)

The FastAPI backend service, managed with `uv`.

Planned structure (per `planning/01-architecture.md` / `planning/03-backend.md`):

- `app/` — HTTP layer (routers, deps, auth, quota, OTel wiring)
- `lengua_core/` — ported domain logic (LLM provider seam, scheduler, proficiency, prompts, models)
- `migrations/` — Alembic
- `tests/`
- `Dockerfile`, `pyproject.toml`

> Placeholder. Scaffolded in Phase 0 group 0.2; the legacy Streamlit app moves into
> `legacy_streamlit/` in task 0.1.2.
