import json
from pathlib import Path

import pytest
from support.scenarios import a_history, a_session

from coach.core.errors import Setup
from coach.store.connection import open_store
from coach.store.export import export
from coach.store.rebuild import Rebuilt, rebuild_missing

ENGINE = "0.3.0"


def write_export(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def exported_history(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    with open_store(tmp_path / "first.db") as conn:
        a_history(conn)
    files = dict(export(conn, ENGINE).files)
    conn.close()
    return write_export(tmp_path / "export", files), files


def test_a_missing_database_is_rebuilt_from_the_export_byte_for_byte(tmp_path: Path) -> None:
    export_dir, files = exported_history(tmp_path)
    database = tmp_path / "coach.db"

    rebuilt = rebuild_missing(database, export_dir)

    assert rebuilt == Rebuilt(schema_version=1)
    conn = open_store(database)
    assert export(conn, ENGINE).files == files


def test_the_rebuilt_store_keeps_foreign_keys_on_and_its_rows_readable(tmp_path: Path) -> None:
    export_dir, _ = exported_history(tmp_path)
    database = tmp_path / "coach.db"

    rebuild_missing(database, export_dir)

    conn = open_store(database)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT id FROM check_in WHERE status = 'current'").fetchall() == [
        ("ci-2026-11-01-2",)
    ]


def test_with_no_manifest_nothing_is_rebuilt_and_no_database_is_made(tmp_path: Path) -> None:
    database = tmp_path / "coach.db"

    assert rebuild_missing(database, tmp_path / "export") is None
    assert not database.exists()


def test_with_the_database_present_a_differing_export_is_not_read(tmp_path: Path) -> None:
    export_dir, _ = exported_history(tmp_path)
    database = tmp_path / "coach.db"
    with open_store(database) as conn:
        a_session(conn, "only_local")
    conn.close()

    assert rebuild_missing(database, export_dir) is None

    conn = open_store(database)
    assert conn.execute("SELECT id FROM session").fetchall() == [("only_local",)]
    assert conn.execute("SELECT count(*) FROM workout").fetchone() == (0,)


def test_a_manifest_newer_than_the_engine_stops_with_export_newer_than_engine(
    tmp_path: Path,
) -> None:
    export_dir, files = exported_history(tmp_path)
    manifest = json.loads(files["manifest.json"])
    manifest["schema_version"] = 2
    (export_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    database = tmp_path / "coach.db"

    with pytest.raises(Setup) as raised:
        rebuild_missing(database, export_dir)

    assert raised.value.code == "export_newer_than_engine"
    assert not database.exists()


def test_a_rebuild_that_fails_part_way_leaves_no_database(tmp_path: Path) -> None:
    export_dir, _ = exported_history(tmp_path)
    (export_dir / "weigh_in.jsonl").write_text('{"id":"wi-0001"}\n', encoding="utf-8")
    database = tmp_path / "coach.db"

    with pytest.raises(Exception):  # noqa: B017
        rebuild_missing(database, export_dir)

    assert not database.exists()
    assert list(tmp_path.glob("coach.db*")) == []
