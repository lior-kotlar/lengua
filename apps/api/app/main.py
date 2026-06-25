"""FastAPI application entrypoint.

Exposes a minimal ``GET /health`` liveness probe. The full HTTP surface
(routers, auth, quota, OTel wiring) lands in later Phase 1 tasks.
"""

from fastapi import FastAPI

app = FastAPI(title="Lengua API")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by Cloud Run and CI smoke checks."""
    return {"status": "ok"}
