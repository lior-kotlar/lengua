"""Integration test proving the throwaway Postgres fixture connects and tears down.

Skips automatically when Docker isn't available (see conftest.postgres_url).
"""

from sqlalchemy import Engine, text


def test_connect_create_temp_table_and_teardown(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("CREATE TEMP TABLE probe (id int primary key, name text)"))
        conn.execute(text("INSERT INTO probe (id, name) VALUES (1, 'lengua')"))
        name = conn.execute(text("SELECT name FROM probe WHERE id = 1")).scalar_one()

    assert name == "lengua"
