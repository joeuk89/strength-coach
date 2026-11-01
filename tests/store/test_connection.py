import sqlite3
from pathlib import Path

import pytest

from coach.core.errors import Setup
from coach.store.connection import SCHEMA_VERSION, connect, open_store, schema_version


def test_the_connection_factory_turns_foreign_keys_on() -> None:
    conn = connect(":memory:")

    assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_a_foreign_key_violation_is_refused_by_the_store() -> None:
    conn = open_store(":memory:")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO rehab_session VALUES"
            " ('s', 'n-0001', 't', 'optional', 'daily', NULL, '[]', 'h', 'r')"
        )


def test_a_fresh_database_is_built_at_schema_version_1(tmp_path: Path) -> None:
    conn = open_store(tmp_path / "coach.db")

    assert SCHEMA_VERSION == 1
    assert schema_version(conn) == 1
    tables = {name for (name,) in conn.execute("SELECT name FROM sqlite_master")}
    assert {"week_plan", "workout", "routine_map"} <= tables


def test_reopening_a_current_database_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "coach.db"
    with open_store(path) as conn:
        conn.execute("INSERT INTO session VALUES ('push_a', 'pv-1')")
    conn.close()

    reopened = open_store(path)

    assert reopened.execute("SELECT id FROM session").fetchall() == [("push_a",)]


def test_a_database_behind_the_engine_stops_with_schema_behind(tmp_path: Path) -> None:
    path = tmp_path / "coach.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE session (id TEXT PRIMARY KEY)")
    old.commit()
    old.close()

    with pytest.raises(Setup) as raised:
        open_store(path)

    assert raised.value.code == "schema_behind"
