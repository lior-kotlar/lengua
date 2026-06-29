# apps/api — FastAPI backend

The HTTP backend (deployed to Cloud Run). Scaffold lands in Phase 0 group 0.2; the core
Generate→Save→Review→Discover loop is ported over HTTP in Phase 1.

Planned layout (see [planning/01-architecture.md](../../planning/01-architecture.md)):

```
apps/api/
  lengua_core/      # the ported lengua/* package (gemini, scheduler, proficiency, ...)
  app/              # http layer: routers, deps, auth, quota, otel
  migrations/       # Alembic
  tests/
  Dockerfile
  pyproject.toml
```

Tooling: `uv`, ruff, mypy, pytest + pytest-cov (≥80% gate). LLM provider defaults to Groq
(`llama-3.1-8b-instant`) for all dev/CI, flippable to Gemini via `LLM_PROVIDER`.
