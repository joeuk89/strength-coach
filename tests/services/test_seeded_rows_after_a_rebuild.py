from pathlib import Path

from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config, a_goal
from support.seeded_rows import a_store_seeded_at

from coach.services.program import adopt
from coach.store.connection import connect
from coach.store.export import export
from coach.store.rebuild import Rebuilt, rebuild_missing


def test_an_export_at_v1_rebuilds_and_a_program_line_naming_burpee_adopts(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    for name, text in export(a_store_seeded_at(1), "0.5.0").files.items():
        (export_dir / name).write_text(text, encoding="utf-8")
    database = tmp_path / "coach.db"

    assert rebuild_missing(database, export_dir) == Rebuilt(schema_version=1)

    conn = connect(database)
    a_goal(conn, "strength", ("bb_bench_press",))
    burpees = a_line("burpee", scheme={"name": "hold"}, start_load=None)
    result = adopt(
        conn,
        toml(a_draft(a_session("push", a_line(), burpees))),
        file="draft.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    assert result.dry_run is False
    assert conn.execute(
        "SELECT exercise_id FROM program_line WHERE exercise_id = 'burpee'"
    ).fetchall() == [("burpee",)]
