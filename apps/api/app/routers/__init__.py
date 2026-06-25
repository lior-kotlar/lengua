"""HTTP routers for the Lengua API (Phase 1.5).

Each module exposes an ``APIRouter`` wired into the app by :func:`app.main.create_app`. Routers
are thin: they validate/translate (DTOs in/out, domain errors -> HTTP status codes) and delegate
all logic to ``app.services`` (which own the transaction and never emit SQL outside repositories).
"""
