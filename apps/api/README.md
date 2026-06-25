# apps/api — Lengua API (FastAPI)

The FastAPI backend service, managed with [`uv`](https://docs.astral.sh/uv/) on Python 3.12.

## Structure

- `app/` — HTTP layer: `main.py` (FastAPI app + `GET /health`), `settings.py`
  (pydantic-settings config). Routers, auth, quota, and OTel wiring land in Phase 1.
- `lengua_core/` — domain logic (LLM provider seam, scheduler, proficiency, prompts, models);
  ported here in task 0.1.2 (renamed from the old root `lengua/` package).
- `legacy_streamlit/` — the legacy Streamlit app (`app.py` + `pages/`), relocated here in task
  0.1.2; run with `cd apps/api && streamlit run legacy_streamlit/app.py`.
- `scripts/` — dev/ops scripts (e.g. `verify.py`).
- `tests/` — pytest suite (`test_health.py`, `test_settings.py`).
- `migrations/` — Alembic (Phase 1+).
- `Dockerfile`, `pyproject.toml`.

> `lengua_core/` and `legacy_streamlit/` are pre-existing and intentionally **out of scope**
> for the API's ruff/mypy gate — the configs in `pyproject.toml` target `app/` + `tests/` only.

## Run

Install deps and start the API (serves `GET /health` → `{"status":"ok"}`):

```
cd apps/api
uv sync
uv run uvicorn app.main:app          # http://127.0.0.1:8000/health
```

## Verify (lint + format + types + tests)

Runs ruff (lint + format check), mypy, and pytest with branch coverage (fails under 80%):

```
cd apps/api
uv run python scripts/verify.py
```

Or run the steps individually:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest --cov --cov-branch
```

## Configuration

Settings are read from the environment (and an optional `.env`) via `app/settings.py`. The
documented variables live in the repo-root [`.env.example`](../../.env.example) — copy it to
`.env` and fill in real values. `LLM_PROVIDER` defaults to `groq` and `GROQ_MODEL` to
`llama-3.1-8b-instant` for all dev/CI.
