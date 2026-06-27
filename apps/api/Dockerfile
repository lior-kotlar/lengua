# Lengua API image (task 0.5.5).
#
# Multi-stage uv build:
#   * builder — resolve the *production* deps (no dev group) into a venv from the frozen lockfile
#   * runtime — copy the venv + source onto a slim base, run as a non-root user
#
# Built in CI (Build API image), saved as an artifact, and run in the E2E job with
# LLM_PROVIDER=fake and NO Groq/Gemini keys (so the FakeLLM seam is exercised with zero real
# LLM calls). Locally:
#   docker build -t lengua-api apps/api
#   docker run --rm -p 8000:8000 -e LLM_PROVIDER=fake lengua-api

# Base image is pinned by sha256 DIGEST (not just the `python:3.12-slim` tag) so every build —
# local, CI, and Cloud Run — resolves the byte-identical, multi-arch base, and a silent upstream
# retag can't change what we ship. This is the OCI image-index digest (covers linux/amd64 + arm64).
# To refresh (e.g. for a base-OS security update), re-resolve the tag's current index digest:
#   docker buildx imagetools inspect python:3.12-slim   # copy the top-level Digest
# or, daemonless, read the Docker-Content-Digest header from the Docker Hub registry manifest API.
# (Dependabot's `docker` ecosystem can also bump this `FROM` pin automatically.)

# ── Builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e AS builder

# uv: fast, frozen, reproducible dependency install.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install only the production dependencies first (better layer caching: this layer is
# invalidated only when the lockfile changes, not on every source edit). `--no-dev` drops the
# test/lint toolchain; `--no-install-project` because pyproject sets `package = false`.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ── Runtime ───────────────────────────────────────────────────────────────────
# Same digest-pinned base as the builder stage (keep both in lockstep when refreshing the pin).
FROM python:3.12-slim@sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e AS runtime

# Non-root runtime user.
RUN groupadd --system app && useradd --system --gid app --create-home app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    LLM_PROVIDER=fake

WORKDIR /app

# The resolved virtualenv from the builder.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Application source. `app/` is the HTTP layer; `lengua_core/` carries the provider-agnostic
# LLM seam (incl. FakeLLM) the API imports. `legacy_streamlit/`, `tests/`, and local data are
# excluded via .dockerignore.
COPY --chown=app:app app ./app
COPY --chown=app:app lengua_core ./lengua_core

USER app

EXPOSE 8000

# Liveness probe mirrors the CI/Cloud Run health check.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health').status==200 else 1)"

# Shell form so ${PORT} is expanded at runtime (Cloud Run injects $PORT).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
