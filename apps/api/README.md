# apps/api — Lengua API (FastAPI)

The FastAPI backend service, managed with `uv`.

Planned structure (per `planning/01-architecture.md` / `planning/03-backend.md`):

- `app/` — HTTP layer (routers, deps, auth, quota, OTel wiring) — scaffolded in 0.2.x
- `lengua_core/` — domain logic (LLM provider seam, scheduler, proficiency, prompts, models); ported here in task 0.1.2 (renamed from the old root `lengua/` package)
- `legacy_streamlit/` — the legacy Streamlit app (`app.py` + `pages/`), relocated here in task 0.1.2; run with `cd apps/api && streamlit run legacy_streamlit/app.py`
- `migrations/` — Alembic
- `tests/`
- `Dockerfile`, `pyproject.toml`

> Scaffolded in Phase 0 group 0.2. The `lengua_core/` package and `legacy_streamlit/`
> app landed in task 0.1.2 and the Streamlit app stays runnable.
