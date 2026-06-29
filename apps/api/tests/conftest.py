"""Shared pytest fixtures, including the throwaway Postgres for integration tests."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from tests.seed import DemoData, seed_demo

try:
    from testcontainers.postgres import PostgresContainer
except ImportError:  # pragma: no cover
    PostgresContainer = None

_POSTGRES_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A throwaway Postgres for the whole test session.

    Skips (rather than fails) when Docker isn't available, so the offline unit suite stays
    green locally; CI always has Docker.
    """
    if PostgresContainer is None:  # pragma: no cover
        pytest.skip("testcontainers is not installed")
    try:
        with PostgresContainer(_POSTGRES_IMAGE, driver="psycopg") as container:
            yield container.get_connection_url()
    except Exception as exc:  # pragma: no cover - depends on local Docker availability
        pytest.skip(f"Docker/Postgres testcontainer unavailable: {exc}")


@pytest.fixture
def db_engine(postgres_url: str) -> Iterator[Engine]:
    """A SQLAlchemy engine to a clean ``public`` schema, reset after each test."""
    engine = create_engine(postgres_url)
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()


@pytest.fixture
def demo_account(db_engine: Engine) -> DemoData:
    """The reviewer/demo account + a non-empty deck, seeded into a fresh DB."""
    return seed_demo(db_engine)
