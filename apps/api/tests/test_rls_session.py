"""The backend DB session runs under the authenticated user's identity (task 2.6.2).

Two layers of proof:

* **Wiring (unit, no DB).** The ``app.deps.get_db`` dependency binds the request's session to
  ``current_user`` via :func:`app.db.rls.bind_request_identity`, so every router transparently
  runs under the caller's identity. Proven by calling the dependency directly.
* **Enforcement (integration).** A real :class:`AsyncSession` bound to user A — built exactly like
  the request session — returns **only A's rows** for a *raw* ``SELECT … FROM cards`` that has no
  app-layer ``WHERE user_id`` at all; an identical session bound to B sees only B's; an *unbound*
  (privileged) session sees both (proving it is the binding, not the data, that isolates); and the
  scoping survives a mid-request ``commit()`` (the ``after_begin`` listener re-applies it).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.rls import bind_request_identity
from app.db.session import async_dsn
from app.deps import current_user, get_db
from tests.conftest import _skip_if_db_unreachable, database_url
from tests.rls_helpers import delete_users, seed_user

# ── Wiring: get_db binds the session to current_user (no DB needed) ────────────────────────────


@pytest.mark.asyncio
async def test_get_db_binds_request_identity_to_current_user() -> None:
    """`get_db` stamps the authenticated id onto the session it returns (the RLS choke point)."""
    user_id = uuid.uuid4()
    session = AsyncSession()  # unbound: we only inspect identity wiring, never touch a DB
    try:
        returned = await get_db(session=session, user_id=user_id)
        assert returned is session, "get_db must return the same session it bound"
        # bind_request_identity stashes the id on Session.info so the after_begin listener can read
        # it on every transaction the session opens.
        assert user_id in session.info.values()
    finally:
        await session.close()


def test_get_db_depends_on_current_user() -> None:
    """`get_db` derives identity from ``current_user`` — a session can't exist without a verified
    user (defense-in-depth: no token ⇒ 401 before any DB work)."""
    from typing import get_args, get_type_hints

    hints = get_type_hints(get_db, include_extras=True)
    user_id_meta = get_args(hints["user_id"])[1:]  # the Depends(...) of Annotated[UUID, Depends]
    assert any(getattr(m, "dependency", None) is current_user for m in user_id_meta), (
        "get_db must depend on current_user so RLS identity is always derived from a verified token"
    )


def test_after_begin_is_noop_without_a_bound_identity() -> None:
    """The listener leaves the connection untouched when no identity is stashed (defensive guard).

    A session that was never bound (``info`` has no user id) must not emit ``SET ROLE`` — it would
    otherwise silently switch roles with no claims. Covers the guard's false branch directly.
    """
    from app.db.rls import _after_begin

    session = MagicMock()
    session.info = {}
    connection = MagicMock()
    _after_begin(session, object(), connection)
    connection.execute.assert_not_called()


@pytest.mark.asyncio
async def test_bind_request_identity_is_idempotent() -> None:
    """Re-binding a session updates the stashed id without registering a second listener."""
    from sqlalchemy import event

    from app.db.rls import _after_begin

    first, second = uuid.uuid4(), uuid.uuid4()
    session = AsyncSession()
    try:
        bind_request_identity(session, first)
        bind_request_identity(session, second)  # exercises the already-registered fast path
        assert second in session.info.values() and first not in session.info.values()
        assert event.contains(session.sync_session, "after_begin", _after_begin)
    finally:
        await session.close()


# ── Enforcement against the live stack ─────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bound_session_scopes_raw_select_to_its_user() -> None:
    """A session bound to A (then B) sees only that user's cards on a raw, unfiltered select."""
    _skip_if_db_unreachable()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        a = seed_user(conn)
        b = seed_user(conn)

    engine = create_async_engine(async_dsn(database_url()))
    try:
        for user in (a, b):
            async with AsyncSession(bind=engine) as session:
                bind_request_identity(session, user.id)
                # No app-layer WHERE — RLS alone must scope this.
                rows = (await session.execute(text("SELECT user_id FROM cards"))).all()
                seen = {str(r[0]) for r in rows}
                assert seen == {str(user.id)}, f"{user.id} saw foreign rows: {seen}"
                assert len(rows) == len(user.card_ids)
    finally:
        await engine.dispose()
        with psycopg.connect(database_url(), autocommit=True) as conn:
            delete_users(conn, a, b)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unbound_session_is_not_scoped() -> None:
    """An *unbound* session keeps the privileged connecting role and sees BOTH users' rows.

    This is the control: it proves the isolation in the test above comes from the per-request
    identity binding, not from the seeded data happening to be disjoint.
    """
    _skip_if_db_unreachable()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        a = seed_user(conn)
        b = seed_user(conn)

    engine = create_async_engine(async_dsn(database_url()))
    try:
        async with AsyncSession(bind=engine) as session:
            rows = (
                await session.execute(
                    text("SELECT user_id FROM cards WHERE user_id = ANY(:ids)"),
                    {"ids": [a.id, b.id]},
                )
            ).all()
            seen = {str(r[0]) for r in rows}
            assert seen == {str(a.id), str(b.id)}, f"privileged session was scoped: {seen}"
    finally:
        await engine.dispose()
        with psycopg.connect(database_url(), autocommit=True) as conn:
            delete_users(conn, a, b)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_identity_survives_commit() -> None:
    """The identity is re-applied after a mid-request ``commit()`` (the ``after_begin`` listener).

    ``SET LOCAL`` / ``set_config(is_local := true)`` are cleared when a transaction ends, so a
    naive one-shot ``SET`` would silently fall back to the privileged role after the first commit.
    The listener re-applies on every transaction begin — proven here by querying again post-commit.
    """
    _skip_if_db_unreachable()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        a = seed_user(conn)
        b = seed_user(conn)

    engine = create_async_engine(async_dsn(database_url()))
    try:
        async with AsyncSession(bind=engine) as session:
            bind_request_identity(session, a.id)
            first = (await session.execute(text("SELECT user_id FROM cards"))).all()
            assert {str(r[0]) for r in first} == {str(a.id)}

            await session.commit()  # ends the txn; local role/claims are dropped by Postgres

            # A brand-new transaction autobegins here; if the listener did not re-apply, this would
            # run as the privileged role and leak B's rows.
            second = (await session.execute(text("SELECT user_id FROM cards"))).all()
            assert {str(r[0]) for r in second} == {str(a.id)}, "identity lost after commit"
            assert len(second) == len(a.card_ids)
    finally:
        await engine.dispose()
        with psycopg.connect(database_url(), autocommit=True) as conn:
            delete_users(conn, a, b)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_get_db_scopes_an_http_request_end_to_end() -> None:
    """A real HTTP request through the **un-overridden** ``get_db`` runs under ``authenticated``.

    Every other API test overrides ``get_db`` with a privileged test session, so this is the one
    test that drives the production wiring: the scoped ``get_db`` binds the request session to
    ``current_user`` and a normal write→read round-trip (``POST`` then ``GET /languages``) succeeds
    under the ``authenticated`` role with RLS active — catching any role/privilege regression in the
    real path (only the raw session sub-dependency is swapped for a loop-local engine). The created
    row lands committed and stamped with the caller's id, satisfying the ``WITH CHECK`` clause.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import get_db as raw_get_db
    from app.deps import get_llm_provider
    from app.main import create_app
    from lengua_core.llm.fake import FakeLLM
    from tests.auth_helpers import authenticate_as

    _skip_if_db_unreachable()
    uid = uuid.uuid4()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
            (uid, f"rp-{uid.hex[:8]}@lengua.test"),
        )

    engine = create_async_engine(async_dsn(database_url()))
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _raw_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app = create_app()
    # Swap ONLY the raw session sub-dependency (for a loop-local engine); the scoped get_db that
    # binds the RLS identity still runs for real. Authenticate as our seeded user; FakeLLM unused.
    app.dependency_overrides[raw_get_db] = _raw_session
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    authenticate_as(app, uid)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post("/languages", json={"name": "RealPath"})
            assert created.status_code == 200, created.text
            listed = await client.get("/languages")
            assert listed.status_code == 200
            assert "RealPath" in [lang["name"] for lang in listed.json()]

        # The write committed under the authenticated role, stamped with the caller's id.
        with psycopg.connect(database_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT user_id FROM languages WHERE name = 'RealPath' AND user_id = %s", (uid,)
            ).fetchone()
            assert row is not None, "POST /languages did not persist under RLS"
    finally:
        await engine.dispose()
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM auth.users WHERE id = %s", (uid,))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_get_db_persists_the_full_write_loop_under_rls() -> None:
    """Every *other* write the app makes round-trips through the **un-overridden** ``get_db``.

    The sibling test above only exercises ``/languages``. Every other API test overrides ``get_db``
    with a privileged, RLS-bypassing session, so the production write path for cards/reviews/
    proficiency/settings is never actually run under the ``authenticated`` role + ``WITH CHECK`` +
    role grants. This drives all of them through the real scoped session:

    * ``POST /cards/save`` — INSERT ``cards`` (identity PK ⇒ needs the sequence grant + WITH CHECK);
    * ``POST /review/{id}/grade`` — UPDATE ``cards`` + INSERT ``reviews`` (identity PK) + upsert
      ``proficiency``, committed together; and
    * ``PUT /proficiency`` / ``PUT /settings`` — the two composite-PK ``ON CONFLICT`` upserts.

    A missing INSERT/UPDATE grant, an un-granted identity sequence, or a repository that forgets to
    stamp ``user_id`` (which the policy's ``WITH CHECK`` then rejects) would 500 *here* — instead of
    on the first real production write while CI stays green. Each row is read back with a privileged
    connection and asserted to be committed and stamped with the caller's id.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import get_db as raw_get_db
    from app.deps import get_llm_provider
    from app.main import create_app
    from lengua_core.llm.fake import FakeLLM
    from tests.auth_helpers import authenticate_as

    _skip_if_db_unreachable()
    uid = uuid.uuid4()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
            (uid, f"loop-{uid.hex[:8]}@lengua.test"),
        )

    engine = create_async_engine(async_dsn(database_url()))
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def _raw_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app = create_app()
    # Swap ONLY the raw session sub-dependency (loop-local engine); the scoped get_db that binds the
    # RLS identity still runs for real, so every write below executes as the authenticated role.
    app.dependency_overrides[raw_get_db] = _raw_session
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    authenticate_as(app, uid)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # INSERT languages (identity PK + WITH CHECK) — the language the rest hangs off.
            lang = await client.post("/languages", json={"name": "Loop", "code": "es"})
            assert lang.status_code == 200, lang.text
            language_id = int(lang.json()["id"])

            # Build previews with the FakeLLM (no DB write) then INSERT cards (identity PK).
            gen = await client.post(
                "/generate", json={"language_id": language_id, "words": ["hola", "gato"]}
            )
            assert gen.status_code == 200, gen.text
            previews = gen.json()
            assert len(previews) > 0
            saved = await client.post(
                "/cards/save", json={"language_id": language_id, "cards": previews}
            )
            assert saved.status_code == 200, saved.text
            assert len(saved.json()) == len(previews)

            # Grade a new card: UPDATE cards + INSERT reviews + upsert proficiency, all committed in
            # one authenticated-role transaction (and re-applied across the service's commit()).
            due = await client.get("/review/due", params={"language_id": language_id})
            assert due.status_code == 200, due.text
            target = due.json()["new"][0]
            graded = await client.post(f"/review/{target['id']}/grade", json={"rating": 4})
            assert graded.status_code == 200, graded.text

            # Composite-PK ON CONFLICT upserts (proficiency already has a row from the grade above,
            # so this exercises the DO UPDATE branch; settings is a fresh INSERT).
            prof = await client.put(f"/proficiency/{language_id}", json={"band": "B1"})
            assert prof.status_code == 200, prof.text
            prof_score = float(prof.json()["score"])
            settings = await client.put("/settings", json={"values": {"daily_new_limit": "5"}})
            assert settings.status_code == 200, settings.text

        # Every write committed under the authenticated role, stamped with the caller's id. Read
        # back over a privileged (RLS-bypassing) connection so we see exactly what landed.
        with psycopg.connect(database_url(), autocommit=True) as conn:
            cards_n = conn.execute(
                "SELECT count(*) FROM cards WHERE user_id = %s AND language_id = %s",
                (uid, language_id),
            ).fetchone()
            assert cards_n is not None and cards_n[0] == len(previews), (
                "POST /cards/save did not persist all cards under RLS"
            )

            review = conn.execute(
                "SELECT user_id FROM reviews WHERE card_id = %s", (target["id"],)
            ).fetchone()
            assert review is not None and review[0] == uid, (
                "POST /review/grade did not log a review stamped with the caller's id"
            )

            rescheduled = conn.execute(
                "SELECT due FROM cards WHERE id = %s AND user_id = %s", (target["id"], uid)
            ).fetchone()
            assert rescheduled is not None and rescheduled[0] is not None, (
                "grade did not UPDATE the graded card's schedule under RLS"
            )

            prof_row = conn.execute(
                "SELECT score FROM proficiency WHERE user_id = %s AND language_id = %s",
                (uid, language_id),
            ).fetchone()
            assert prof_row is not None and prof_row[0] == pytest.approx(prof_score), (
                "PUT /proficiency upsert did not persist the override under RLS"
            )

            setting = conn.execute(
                "SELECT value FROM user_settings WHERE user_id = %s AND key = 'daily_new_limit'",
                (uid,),
            ).fetchone()
            assert setting is not None and setting[0] == "5", (
                "PUT /settings upsert did not persist under RLS"
            )
    finally:
        await engine.dispose()
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM auth.users WHERE id = %s", (uid,))
