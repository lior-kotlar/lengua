# syntax=docker/dockerfile:1
FROM python:3.13-slim

# uv for fast, reproducible installs from the committed lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime deps first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App code.
COPY app ./app
COPY lengua_core ./lengua_core

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
