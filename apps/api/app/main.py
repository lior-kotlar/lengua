"""FastAPI application entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="Lengua API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by CI, Cloud Run, and uptime checks."""
    return {"status": "ok"}
