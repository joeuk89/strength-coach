import json
from pathlib import Path
from typing import Any

from support.scenarios import a_catalogue_without

from coach.store.catalogue import merge_catalogue, seed_catalogue
from coach.store.connection import open_store

BUILT_IN_TEMPLATES = Path(__file__).parents[1] / "fixtures/hevy/built_in_exercise_templates.json"

EXERCISE_COLUMNS = [
    "id",
    "name",
    "load_mode",
    "equipment_kind",
    "pattern",
    "muscles",
    "hevy_title",
    "hevy_exercise_type",
    "hevy_equipment",
    "hevy_muscle_group",
    "hevy_template_id",
    "source",
]


def seeded() -> list[dict[str, Any]]:
    conn = open_store(":memory:")
    seed_catalogue(conn)
    cursor = conn.execute("SELECT * FROM exercise ORDER BY id")
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor]


def test_the_seed_inserts_every_catalogue_row_and_reports_the_count() -> None:
    conn = open_store(":memory:")

    count = seed_catalogue(conn)

    assert count == conn.execute("SELECT count(*) FROM exercise").fetchone()[0]
    assert count >= 114


def test_every_seeded_row_is_a_catalogue_row() -> None:
    assert {row["source"] for row in seeded()} == {"catalogue"}


def test_no_two_rows_share_a_hevy_template_id() -> None:
    template_ids = [row["hevy_template_id"] for row in seeded() if row["hevy_template_id"]]

    assert len(template_ids) == len(set(template_ids))


def test_every_row_with_a_built_in_equivalent_carries_its_template_id() -> None:
    template_ids = [row["hevy_template_id"] for row in seeded() if row["hevy_template_id"]]

    assert len(template_ids) == 127


def test_each_template_id_is_the_built_in_template_of_the_row_hevy_title() -> None:
    built_in = {t["id"]: t["title"] for t in json.loads(BUILT_IN_TEMPLATES.read_text())}

    for row in seeded():
        if row["hevy_template_id"]:
            assert built_in[row["hevy_template_id"]] == row["hevy_title"], row["id"]


def test_a_row_carries_the_library_columns_and_nothing_about_an_athlete() -> None:
    for row in seeded():
        assert list(row) == EXERCISE_COLUMNS


def test_a_row_without_a_template_id_carries_no_create_columns() -> None:
    for row in seeded():
        if row["hevy_template_id"] is None:
            create = (row["hevy_exercise_type"], row["hevy_equipment"], row["hevy_muscle_group"])
            assert create == (None, None, None), row["id"]


def test_muscles_hold_a_primary_and_a_secondary_list() -> None:
    for row in seeded():
        muscles = json.loads(row["muscles"])
        assert list(muscles) == ["primary", "secondary"], row["id"]
        assert muscles["primary"], row["id"]


def test_known_lifts_carry_their_load_mode_equipment_kind_and_pattern() -> None:
    rows = {row["id"]: row for row in seeded()}

    assert {
        exercise: (
            rows[exercise]["load_mode"],
            rows[exercise]["equipment_kind"],
            rows[exercise]["pattern"],
        )
        for exercise in (
            "bb_bench_press",
            "db_bench_press",
            "pull_up",
            "trap_bar_deadlift",
            "plank",
        )
    } == {
        "bb_bench_press": ("total", "barbell", "horizontal_push"),
        "db_bench_press": ("per_hand_x2", "dumbbell", "horizontal_push"),
        "pull_up": ("bodyweight", "bodyweight", "vertical_pull"),
        "trap_bar_deadlift": ("total", "barbell", "hinge"),
        "plank": ("duration", "bodyweight", "core"),
    }


def row(conn: Any, exercise_id: str) -> tuple[Any, ...]:
    return conn.execute("SELECT * FROM exercise WHERE id = ?", (exercise_id,)).fetchone()


def test_the_merge_inserts_a_catalogue_id_the_store_lacks_and_leaves_an_edited_row_as_it_is() -> (
    None
):
    seeded_whole = open_store(":memory:")
    seed_catalogue(seeded_whole)
    shipped = row(seeded_whole, "assisted_dip")
    conn = open_store(":memory:")
    a_catalogue_without(conn, "assisted_dip")
    conn.execute(
        "UPDATE exercise SET name = 'Rollout, kneeling', hevy_template_id = 'A1B2C3D4',"
        " source = 'record' WHERE id = 'ab_wheel'"
    )
    edited = row(conn, "ab_wheel")

    inserted = merge_catalogue(conn)

    assert inserted == ("assisted_dip",)
    assert row(conn, "ab_wheel") == edited
    assert row(conn, "assisted_dip") == shipped


def test_the_merge_on_a_store_holding_every_catalogue_id_inserts_nothing() -> None:
    conn = open_store(":memory:")
    seed_catalogue(conn)

    assert merge_catalogue(conn) == ()
