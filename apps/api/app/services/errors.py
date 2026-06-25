"""Domain errors raised by the service layer.

Services raise these provider-agnostic errors instead of leaking HTTP or SQL concerns; the
FastAPI routers (Phase 1.5) translate them to status codes (``NotFoundError`` -> 404,
``ValidationError`` -> 422/400). Repositories stay exception-free — they return ``None`` / an
empty result and let the service decide whether that is an error.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for all service-layer domain errors."""


class NotFoundError(ServiceError):
    """A referenced resource does not exist or is not owned by the requesting user."""


class ValidationError(ServiceError):
    """The caller supplied invalid input (empty name, unknown CEFR band, …)."""
