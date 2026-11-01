import json
from pathlib import Path

import pytest
from support.cli import run_coach
from support.instances import an_instance
from support.scenarios import a_history, a_session

from coach.cli import app, registry
from coach.cli.declaration import Call, Declaration, Example, Outcome, Writes
from coach.store.connection import open_store
from coach.store.export import export

ENGINE = "0.3.0"


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An instance whose store holds a small history and whose export was written from it."""
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path / "athlete", pin=ENGINE)
    (root / ".coach").mkdir()
    with open_store(root / ".coach" / "coach.db") as conn:
        a_history(conn)
    files = export(conn, ENGINE).files
    conn.close()
    (root / "export").mkdir()
    for name, text in files.items():
        (root / "export" / name).write_text(text, encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def export_files(root: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted((root / "export").iterdir())}


def a_stub_verb(monkeypatch: pytest.MonkeyPatch, *, writes: Writes) -> None:
    """A verb that writes nothing itself and reports what the CLI handed it."""

    def run(call: Call) -> Outcome:
        rebuilt = call.rebuilt
        return Outcome({"rebuilt": None if rebuilt is None else rebuilt.schema_version})

    stub = Declaration(
        name="stub",
        summary="test only",
        writes=writes,
        needs_instance=True,
        output={"type": "object"},
        run=run,
        examples=(Example(("stub",), "test only"),),
    )
    known = registry.declarations()
    monkeypatch.setattr(registry, "declarations", lambda: (*known, stub))


def test_deleting_the_database_then_any_verb_rebuilds_it_and_re_exports_byte_identical(
    instance: Path,
) -> None:
    before = export_files(instance)
    (instance / ".coach" / "coach.db").unlink()

    assert run_coach("status").code == 0
    dry_run = run_coach("publish", "--dry-run")

    written = dry_run.envelope["result"]["written"]
    assert [path for path in written if path.startswith("export/")] == []
    with open_store(instance / ".coach" / "coach.db") as conn:
        again = export(conn, ENGINE).files
    conn.close()
    assert {name: text.encode() for name, text in again.items()} == before


def test_the_verb_after_a_rebuild_is_handed_the_manifest_schema_version(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_stub_verb(monkeypatch, writes="store")
    (instance / ".coach" / "coach.db").unlink()

    rebuilt = run_coach("stub")
    again = run_coach("stub")

    assert rebuilt.envelope["result"] == {"rebuilt": 1}
    assert again.envelope["result"] == {"rebuilt": None}


def test_a_manifest_newer_than_the_engine_stops_with_export_newer_than_engine(
    instance: Path,
) -> None:
    manifest_path = instance / "export" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_path.write_text(json.dumps({**manifest, "schema_version": 2}))
    (instance / ".coach" / "coach.db").unlink()

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "export_newer_than_engine"
    assert not (instance / ".coach" / "coach.db").exists()


def test_with_the_database_present_a_differing_export_is_not_read(instance: Path) -> None:
    session = instance / "export" / "session.jsonl"
    session.write_text(session.read_text() + '{"id":"from_elsewhere","introduced_in":"pv-9"}\n')

    assert run_coach("status").code == 0

    with open_store(instance / ".coach" / "coach.db") as conn:
        ids = {row[0] for row in conn.execute("SELECT id FROM session")}
    conn.close()
    assert ids == {"upper_a", "lower_a"}


def test_a_manifest_row_count_above_the_store_is_reported_by_status(instance: Path) -> None:
    database = instance / ".coach" / "coach.db"
    database.unlink()
    open_store(database).close()

    run = run_coach("status")

    assert run.code == 0
    assert run.envelope["result"]["export"] == {"behind_store": True, "store_behind_export": True}


def test_a_store_write_refuses_with_store_behind_export_naming_the_tables(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_stub_verb(monkeypatch, writes="store")
    database = instance / ".coach" / "coach.db"
    database.unlink()
    with open_store(database) as conn:
        a_session(conn, "upper_a")
    conn.close()

    run = run_coach("stub")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "store_behind_export"
    assert "session" in run.envelope["error"]["message"]
    assert "workout" in run.envelope["error"]["message"]


def test_a_read_still_runs_on_a_store_behind_the_export(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_stub_verb(monkeypatch, writes="none")
    database = instance / ".coach" / "coach.db"
    database.unlink()
    open_store(database).close()

    assert run_coach("stub").code == 0
