import sqlite3
from pathlib import Path

import pytest
from support.chains import TEMPORARY

from coach.store.chain import ENGINE, Chain, Migrated, migrate
from coach.store.connection import connect, schema_version
from coach.store.export import export
from coach.store.rebuild import Rebuilt, rebuild_missing


def at_version(chain: Chain, version: int) -> sqlite3.Connection:
    conn = connect(":memory:")
    conn.executescript(chain.ddl(version))
    conn.execute(f"PRAGMA user_version = {version}")
    return conn


def schema_of(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return conn.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()


def a_v1_store_with_rows() -> sqlite3.Connection:
    conn = at_version(TEMPORARY, 1)
    with conn:
        conn.execute("INSERT INTO kind VALUES ('k1', 'a'), ('k2', 'b')")
        conn.execute("INSERT INTO item VALUES ('i1', 'k1'), ('i2', 'k2')")
    return conn


@pytest.mark.parametrize("chain", [ENGINE, TEMPORARY], ids=["engine", "temporary"])
def test_every_frozen_ddl_migrates_to_the_current_schema(chain: Chain) -> None:
    current = schema_of(at_version(chain, chain.version))
    for version in range(1, chain.version):
        conn = at_version(chain, version)

        migrate(conn, chain)

        assert schema_version(conn) == chain.version
        assert schema_of(conn) == current


def test_the_engine_carries_one_frozen_ddl_per_past_version() -> None:
    assert set(ENGINE.frozen) == set(range(1, ENGINE.version))


def test_a_migration_moves_the_version_and_keeps_every_row() -> None:
    conn = a_v1_store_with_rows()

    migrated = migrate(conn, TEMPORARY)

    assert migrated == Migrated(from_version=1, to_version=2, steps=("m0001",))
    assert schema_version(conn) == 2
    assert conn.execute("SELECT * FROM item_label ORDER BY id").fetchall() == [
        ("i1", "a"),
        ("i2", "b"),
    ]


def test_a_check_change_rebuilds_the_table_under_the_new_check_with_foreign_keys_on() -> None:
    conn = a_v1_store_with_rows()

    migrate(conn, TEMPORARY)

    conn.execute("INSERT INTO kind VALUES ('k3', 'c')")
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO item VALUES ('i3', 'no_such_kind')")


def test_a_store_at_the_current_version_runs_no_migration() -> None:
    conn = at_version(TEMPORARY, 2)

    assert migrate(conn, TEMPORARY) == Migrated(from_version=2, to_version=2, steps=())


def test_a_failing_migration_leaves_the_version_and_the_rows_as_they_were() -> None:
    def breaks(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM item")
        raise RuntimeError("migration failed")

    broken = Chain(current=TEMPORARY.current, frozen=TEMPORARY.frozen, steps=(breaks,))
    conn = a_v1_store_with_rows()

    with pytest.raises(RuntimeError):
        migrate(conn, broken)

    assert schema_version(conn) == 1
    assert conn.execute("SELECT count(*) FROM item").fetchone() == (2,)
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_a_migration_that_orphans_a_row_is_rolled_back() -> None:
    def orphans(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM kind WHERE id = 'k1'")

    broken = Chain(current=TEMPORARY.current, frozen=TEMPORARY.frozen, steps=(orphans,))
    conn = a_v1_store_with_rows()

    with pytest.raises(sqlite3.IntegrityError):
        migrate(conn, broken)

    assert schema_version(conn) == 1
    assert conn.execute("SELECT count(*) FROM kind").fetchone() == (2,)


def test_an_export_at_version_n_rebuilds_through_the_frozen_ddl_and_migrates_with_identical_rows(
    tmp_path: Path,
) -> None:
    files = export(a_v1_store_with_rows(), "0.3.0").files
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    for name, text in files.items():
        (export_dir / name).write_text(text, encoding="utf-8")
    database = tmp_path / "coach.db"

    rebuilt = rebuild_missing(database, export_dir, TEMPORARY)

    assert rebuilt == Rebuilt(schema_version=1)
    conn = connect(database)
    assert schema_version(conn) == 2
    again = export(conn, "0.3.0").files
    assert {n: t for n, t in again.items() if n != "manifest.json"} == {
        n: t for n, t in files.items() if n != "manifest.json"
    }
    assert '"schema_version": 2' in again["manifest.json"]


V1_DECISION = (
    "INSERT INTO decision (id, kind, params, because, text, draft_hash, recorded_at) "
    "VALUES (?, ?, '{}', ?, 'agreed', 'sha256:x', '2026-10-30T12:00:00Z')"
)


def test_m0001_keeps_every_decision_and_takes_ladder_rung_and_the_reason_progress() -> None:
    conn = at_version(ENGINE, 1)
    with conn:
        conn.execute(V1_DECISION, ("d-0001", "against_research", "coach_judgement"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(V1_DECISION, ("d-0002", "ladder_rung", "progress"))

    migrate(conn)

    with conn:
        conn.execute(V1_DECISION, ("d-0002", "ladder_rung", "progress"))
    assert conn.execute(
        "SELECT id, kind, because FROM decision_in_force ORDER BY id"
    ).fetchall() == [
        ("d-0001", "against_research", "coach_judgement"),
        ("d-0002", "ladder_rung", "progress"),
    ]
