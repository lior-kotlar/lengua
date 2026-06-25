"""Pydantic request/response DTOs for the HTTP API (Phase 1.5).

These are the wire contract — the shapes the routers accept and return — kept separate from the
ORM models (``app.db.models``) and the pure domain types (``lengua_core``). Output models set
``from_attributes=True`` so they can be validated directly from ORM rows / domain dataclasses.
"""
