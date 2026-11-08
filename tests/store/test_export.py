import json

from support.scenarios import a_session, a_workout, an_exercise

from coach.store.chain import ENGINE as CHAIN
from coach.store.connection import open_store
from coach.store.export import Manifest, export, tables_behind


def test_a_table_exports_one_line_per_row_sorted_by_key_with_keys_in_column_order() -> None:
    conn = open_store(":memory:")
    a_session(conn, "upper_b")
    a_session(conn, "lower_a")
    a_session(conn, "Upper_a")

    files = export(conn, "0.3.0").files

    assert files["session.jsonl"] == (
        '{"id":"Upper_a","introduced_in":"pv-1"}\n'
        '{"id":"lower_a","introduced_in":"pv-1"}\n'
        '{"id":"upper_b","introduced_in":"pv-1"}\n'
    )


def test_a_multi_column_key_sorts_column_by_column_and_integers_numerically() -> None:
    conn = open_store(":memory:")
    an_exercise(conn, "bb_bench_press")
    a_workout(conn, "w-0001", "2026-11-02T10:00:00Z", sets=11)

    lines = export(conn, "0.3.0").files["logged_set.jsonl"].splitlines()

    positions = [json.loads(line)["position"] for line in lines]
    assert positions == list(range(1, 12))


def test_null_is_written_as_null_and_text_keeps_its_characters() -> None:
    conn = open_store(":memory:")
    an_exercise(conn, "bb_bench_press", name="Bänkpress")

    (line,) = export(conn, "0.3.0").files["exercise.jsonl"].splitlines()

    assert line == (
        '{"id":"bb_bench_press","name":"Bänkpress","load_mode":"total",'
        '"equipment_kind":"barbell","pattern":"horizontal_push",'
        '"muscles":"{\\"primary\\":[\\"chest\\"],\\"secondary\\":[]}",'
        '"hevy_title":null,"hevy_exercise_type":null,"hevy_equipment":null,'
        '"hevy_muscle_group":null,"hevy_template_id":null,"source":"record"}'
    )


def test_the_manifest_names_the_versions_and_every_table_count_sorted_by_name() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")
    a_session(conn, "pull_a")

    files = export(conn, "0.3.0").files

    manifest = json.loads(files["manifest.json"])
    assert list(manifest) == ["schema_version", "engine_version", "tables"]
    assert manifest["schema_version"] == CHAIN.version
    assert manifest["engine_version"] == "0.3.0"
    assert manifest["tables"]["session"] == 2
    assert manifest["tables"]["workout"] == 0
    assert list(manifest["tables"]) == sorted(manifest["tables"])
    assert len(manifest["tables"]) == 35


def test_every_table_has_a_file_and_no_view_does() -> None:
    files = export(open_store(":memory:"), "0.3.0").files

    assert "session.jsonl" in files
    assert files["session.jsonl"] == ""
    assert "workout_current.jsonl" not in files
    assert "plan_in_force.jsonl" not in files
    assert len(files) == 36


def test_an_unchanged_store_exports_the_same_bytes() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")

    assert export(conn, "0.3.0") == export(conn, "0.3.0")


def test_a_table_with_more_rows_in_the_manifest_than_the_store_is_behind_the_export() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")
    manifest = Manifest(
        schema_version=1, engine_version="0.3.0", tables={"session": 2, "workout": 0}
    )

    assert tables_behind(conn, manifest) == ("session",)


def test_a_store_with_as_many_or_more_rows_is_not_behind_the_export() -> None:
    conn = open_store(":memory:")
    a_session(conn, "push_a")
    a_session(conn, "pull_a")
    manifest = Manifest(schema_version=1, engine_version="0.3.0", tables={"session": 1})

    assert tables_behind(conn, manifest) == ()
