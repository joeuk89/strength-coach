import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path

import pytest
from support.chains import TEMPORARY

from coach.store import week_plans
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


def an_export_dir(tmp_path: Path, files: Mapping[str, str]) -> Path:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    for name, text in files.items():
        (export_dir / name).write_text(text, encoding="utf-8")
    return export_dir


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
    database = tmp_path / "coach.db"

    rebuilt = rebuild_missing(database, an_export_dir(tmp_path, files), TEMPORARY)

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


def with_unpositioned_prescriptions(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Rows as a store below version 3 holds them, written out of exercise order."""
    with conn:
        conn.execute(
            "INSERT INTO session VALUES ('lower', 'pv-1'), ('upper', 'pv-1'), ('core', 'pv-1')"
        )
        for id_ in ("ab_wheel", "bb_back_squat", "bb_bench_press"):
            conn.execute(
                "INSERT INTO exercise (id, name, load_mode, equipment_kind, pattern, muscles, "
                "source) VALUES (?, ?, 'total', 'barbell', 'squat', '{}', 'catalogue')",
                (id_, id_),
            )
        for plan, status in (("wp-2026-11-02", "superseded"), ("wp-2026-11-02-2", "approved")):
            conn.execute(
                "INSERT INTO week_plan (id, week, position, status, approved_at, write_plan_hash, "
                "draft_hash, recorded_at) VALUES (?, '2026-11-02', 'A', ?, "
                "'2026-11-01T08:00:00Z', 'sha256:w', 'sha256:d', '2026-11-01T08:00:00Z')",
                (plan, status),
            )
        for plan, session, day, exercise in (
            ("wp-2026-11-02", "lower", "2026-11-02", "bb_bench_press"),
            ("wp-2026-11-02", "core", "2026-11-02", "bb_back_squat"),
            ("wp-2026-11-02", "lower", "2026-11-02", "ab_wheel"),
            ("wp-2026-11-02", "lower", "2026-11-02", "bb_back_squat"),
            ("wp-2026-11-02", "lower", "2026-11-05", "bb_bench_press"),
            ("wp-2026-11-02", "upper", "2026-11-03", "bb_bench_press"),
            ("wp-2026-11-02-2", "lower", "2026-11-02", "bb_bench_press"),
        ):
            conn.execute(
                "INSERT INTO prescription (plan_id, session_id, date, exercise_id, set_groups, "
                "derived_from, steps, flags, change) "
                "VALUES (?, ?, ?, ?, '[]', 'start_load', '[]', '[]', 'held')",
                (plan, session, day, exercise),
            )
    return conn


def positions(
    conn: sqlite3.Connection, plan_id: str = "wp-2026-11-02"
) -> list[tuple[object, object, object, object]]:
    return [
        (r["session_id"], r["date"], r["exercise_id"], r["position"])
        for r in week_plans.prescriptions(conn, plan_id)
    ]


NUMBERED_ACROSS_THE_PLAN = [
    ("core", "2026-11-02", "bb_back_squat", 1),
    ("lower", "2026-11-02", "ab_wheel", 2),
    ("lower", "2026-11-02", "bb_back_squat", 3),
    ("lower", "2026-11-02", "bb_bench_press", 4),
    ("upper", "2026-11-03", "bb_bench_press", 5),
    ("lower", "2026-11-05", "bb_bench_press", 6),
]


def test_m0002_numbers_a_v2_stores_rows_across_each_plan_in_the_order_readers_showed_them() -> None:
    conn = with_unpositioned_prescriptions(at_version(ENGINE, 2))

    migrated = migrate(conn)

    assert migrated.steps == ("m0002",)
    assert positions(conn) == NUMBERED_ACROSS_THE_PLAN
    assert positions(conn, "wp-2026-11-02-2") == [("lower", "2026-11-02", "bb_bench_press", 1)]


def test_a_v1_store_with_prescriptions_migrates_through_both_steps() -> None:
    conn = with_unpositioned_prescriptions(at_version(ENGINE, 1))

    migrated = migrate(conn)

    assert migrated.steps == ("m0001", "m0002")
    assert positions(conn) == NUMBERED_ACROSS_THE_PLAN


def test_a_migrated_prescription_table_has_a_fresh_stores_definition() -> None:
    conn = with_unpositioned_prescriptions(at_version(ENGINE, 2))
    fresh = at_version(ENGINE, ENGINE.version)

    migrate(conn)

    definition = "SELECT sql FROM sqlite_master WHERE name = 'prescription'"
    assert conn.execute(definition).fetchall() == fresh.execute(definition).fetchall()


def test_an_export_written_at_v2_rebuilds_with_its_prescriptions_numbered(tmp_path: Path) -> None:
    files = export(with_unpositioned_prescriptions(at_version(ENGINE, 2)), "0.6.0").files
    assert "position" not in json.loads(files["prescription.jsonl"].splitlines()[0])
    database = tmp_path / "coach.db"

    rebuilt = rebuild_missing(database, an_export_dir(tmp_path, files))

    assert rebuilt == Rebuilt(schema_version=2)
    conn = connect(database)
    assert schema_version(conn) == ENGINE.version
    assert positions(conn) == NUMBERED_ACROSS_THE_PLAN
    first = json.loads(export(conn, "0.6.0").files["prescription.jsonl"].splitlines()[0])
    assert list(first)[:5] == ["plan_id", "session_id", "date", "exercise_id", "position"]
