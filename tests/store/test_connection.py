import sqlite3
from pathlib import Path

import pytest
from support.chains import TEMPORARY, TEMPORARY_V1

from coach.core.errors import Setup
from coach.store.chain import ENGINE
from coach.store.connection import (
    connect,
    copy_to_memory,
    open_store,
    open_store_behind,
    schema_version,
)


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


def test_a_fresh_database_is_built_at_the_engines_schema_version(tmp_path: Path) -> None:
    conn = open_store(tmp_path / "coach.db")

    assert schema_version(conn) == ENGINE.version
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


def a_temporary_store_at_version_1(path: Path) -> None:
    old = connect(path)
    old.executescript(TEMPORARY_V1)
    old.execute("PRAGMA user_version = 1")
    old.close()


def test_a_store_behind_its_chain_stops_with_schema_behind_and_is_left_at_its_version(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coach.db"
    a_temporary_store_at_version_1(path)

    with pytest.raises(Setup) as raised:
        open_store(path, TEMPORARY)

    assert raised.value.code == "schema_behind"
    assert schema_version(open_store_behind(path, TEMPORARY)) == 1


def test_an_in_memory_copy_takes_writes_the_store_never_sees(tmp_path: Path) -> None:
    path = tmp_path / "coach.db"
    conn = open_store(path)
    copy = copy_to_memory(conn)

    copy.execute("INSERT INTO session VALUES ('push_a', 'pv-1')")
    copy.commit()

    assert copy.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert schema_version(copy) == ENGINE.version
    assert conn.execute("SELECT count(*) FROM session").fetchone() == (0,)
