"""Per-request Row-Level-Security identity for the database session (task 2.6.2).

Supabase enforces RLS by running every end-user query as the **non-privileged**
``authenticated`` role with the request's JWT published as Postgres GUCs, so the policy
expression ``auth.uid()`` resolves to the caller's id. The FastAPI backend, however, connects to
Postgres as a privileged role (``postgres`` — ``rolbypassrls = true`` *and* the owner of the
``public`` tables), which **bypasses RLS entirely**. So to make the database-level policies
actually enforced for application traffic we must, per request, do exactly what PostgREST does:

1. ``SET LOCAL ROLE authenticated`` — drop to the role that owns nothing and has no
   ``BYPASSRLS``, so policies are evaluated; and
2. ``set_config('request.jwt.claims', '{"sub": "<uid>", …}', true)`` — publish the caller's
   claims so ``auth.uid()`` returns ``<uid>``.

Both are applied **transaction-locally** (``SET LOCAL`` / ``is_local := true``) so Postgres
discards them automatically when the request's transaction ends — they can never leak onto the
next request that reuses the same pooled connection. Because a service may ``commit()`` partway
through a request (which ends the transaction and clears the local settings), the identity is
re-applied on **every** transaction the session begins, via an ``after_begin`` event listener
keyed on the user id stashed in :attr:`Session.info`.

Migrations and seed scripts deliberately do **not** go through this path: they open their own
connections as the privileged role and must keep bypassing RLS (they create rows for many users).
This module is only ever wired into the request-scoped session (see :func:`app.deps.get_db`).
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

__all__ = [
    "AUTHENTICATED_ROLE",
    "apply_identity",
    "bind_request_identity",
    "build_jwt_claims",
]

#: The non-privileged Postgres role Supabase uses for authenticated end-user requests. It owns no
#: tables and lacks ``BYPASSRLS``, so — unlike the connecting role — RLS policies are enforced
#: against it. A constant (never interpolated from user input), so it is safe to inline into SQL.
AUTHENTICATED_ROLE = "authenticated"

#: Key under which the request's user id is stashed on :attr:`Session.info` for the listener.
_INFO_KEY = "rls_user_id"


def build_jwt_claims(user_id: uuid.UUID) -> str:
    """The minimal ``request.jwt.claims`` JSON that makes ``auth.uid()`` resolve to ``user_id``.

    Supabase's ``auth.uid()`` reads ``request.jwt.claims ->> 'sub'`` (and ``auth.role()`` reads
    ``->> 'role'``), so a two-key object is all the policies need.
    """
    return json.dumps({"sub": str(user_id), "role": AUTHENTICATED_ROLE})


def apply_identity(connection: Connection, user_id: uuid.UUID) -> None:
    """Assume the ``authenticated`` role and publish ``user_id``'s claims on ``connection``.

    Emits ``SET LOCAL ROLE`` + ``set_config(..., is_local := true)``, so the settings live only
    for the current transaction. Synchronous by design: it is called from the ``after_begin``
    listener, which runs inside SQLAlchemy's greenlet on a **sync** :class:`Connection` even when
    the owning session is an :class:`AsyncSession`.
    """
    connection.execute(text(f"SET LOCAL ROLE {AUTHENTICATED_ROLE}"))
    connection.execute(
        text("SELECT set_config('request.jwt.claims', :claims, true)"),
        {"claims": build_jwt_claims(user_id)},
    )


def _after_begin(session: Session, _transaction: object, connection: Connection) -> None:
    """``after_begin`` hook: (re)apply the session's bound identity to the new transaction."""
    user_id = session.info.get(_INFO_KEY)
    if user_id is not None:
        apply_identity(connection, user_id)


def bind_request_identity(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Bind ``session`` so every transaction it opens runs as ``user_id`` under RLS.

    Stashes the id on :attr:`Session.info` and registers the :func:`_after_begin` listener once on
    the session's underlying sync :class:`Session`. The listener fires on the session's first
    statement (autobegin) and after any commit/rollback, so the identity is in force for *all* of
    the request's work — not just until the first commit. Idempotent: binding the same session
    again only updates the stashed id.
    """
    session.info[_INFO_KEY] = user_id
    sync_session = session.sync_session
    if not event.contains(sync_session, "after_begin", _after_begin):
        event.listen(sync_session, "after_begin", _after_begin)
