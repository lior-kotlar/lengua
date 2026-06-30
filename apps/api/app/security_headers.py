"""Baseline HTTP security-response headers (finding S17).

A tiny Starlette middleware that stamps a fixed set of conservative, framework-agnostic security
headers on **every** API response:

* ``X-Content-Type-Options: nosniff`` — stop browsers MIME-sniffing a response into an unexpected
  (executable) content type;
* ``X-Frame-Options: DENY`` — refuse to be framed (clickjacking defence); this also de-frames the
  framable ``/docs`` Swagger UI, which is why the API needs no restrictive CSP;
* ``Referrer-Policy: no-referrer`` — never leak a referrer from the API surface; and
* ``Strict-Transport-Security: max-age=63072000; includeSubDomains`` — pin HTTPS for two years.
  Safe because Cloud Run only ever serves the API over HTTPS (no plaintext origin to lock out).

Deliberately **no** ``Content-Security-Policy``: the API serves JSON plus the (intentionally
framable) ``/docs`` page, and ``X-Frame-Options: DENY`` already removes the only framing concern.
The SPA's CSP lives where it belongs — on the web tier (``apps/web/vercel.json``).

Wired in :func:`app.main.create_app` **before** the CORS middleware, so CORS stays the outermost
layer and its preflight ``OPTIONS`` short-circuit is untouched (a short-circuited preflight never
reaches this middleware — fine, since a preflight needs only the CORS headers, not these).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi import FastAPI

#: The baseline security headers stamped on every API response. Kept as a module constant so a test
#: can assert the full set is applied (and so a future addition is covered automatically).
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamp the baseline :data:`SECURITY_HEADERS` onto every response.

    Headers are set unconditionally (not ``setdefault``) so the policy is authoritative — no route
    can accidentally weaken it. Mirrors the ``RequestLoggingMiddleware`` pattern already used in the
    app, so the streaming/background-task behaviour is identical to a layer the app already runs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


def configure_security_headers(app: FastAPI) -> None:
    """Install the :class:`SecurityHeadersMiddleware` on ``app``.

    MUST be called before the CORS middleware is added in :func:`app.main.create_app` so that CORS
    remains the outermost layer (each ``add_middleware`` call prepends, so the last added is the
    outermost). That keeps the CORS preflight short-circuit ahead of this middleware and lets CORS
    add its headers on top of these on a normal response.
    """
    app.add_middleware(SecurityHeadersMiddleware)
