import sqlite3

import pytest

from coach.core.errors import Setup
from coach.store.connection import open_store
from coach.store.jsonl import load_rows

SQUAT = (
    '{"id": "bb_back_squat", "name": "Back Squat (Barbell)", "load_mode": "total", '
    '"equipment_kind": "barbell", "pattern": "squat", '
    '"muscles": "{\\"primary\\": [\\"quadriceps\\"], \\"secondary\\": []}", '
    '"hevy_title": "Squat (Barbell)", "hevy_exercise_type": null, "hevy_equipment": null, '
    '"hevy_muscle_group": null, "hevy_template_id": "A1B2C3D4", "source": "catalogue"}'
)


def test_each_line_becomes_one_row_with_its_values() -> None:
    conn = open_store(":memory:")

    count = load_rows(conn, "exercise", SQUAT + "\n")

    assert count == 1
    assert conn.execute("SELECT * FROM exercise").fetchall() == [
        (
            "bb_back_squat",
            "Back Squat (Barbell)",
            "total",
            "barbell",
            "squat",
            '{"primary": ["quadriceps"], "secondary": []}',
            "Squat (Barbell)",
            None,
            None,
            None,
            "A1B2C3D4",
            "catalogue",
        )
    ]


def test_a_row_whose_keys_are_out_of_column_order_is_refused() -> None:
    conn = open_store(":memory:")
    reordered = SQUAT.replace(
        '{"id": "bb_back_squat", "name": "Back Squat (Barbell)", ',
        '{"name": "Back Squat (Barbell)", "id": "bb_back_squat", ',
    )

    with pytest.raises(Setup) as raised:
        load_rows(conn, "exercise", reordered)

    assert raised.value.code == "jsonl_row_malformed"


def test_a_row_with_an_extra_column_is_refused() -> None:
    conn = open_store(":memory:")
    with_increment = SQUAT.replace('"source"', '"increment": 2.5, "source"')

    with pytest.raises(Setup) as raised:
        load_rows(conn, "exercise", with_increment)

    assert raised.value.code == "jsonl_row_malformed"


def test_a_row_that_breaks_a_check_is_refused_by_the_schema() -> None:
    conn = open_store(":memory:")

    with pytest.raises(sqlite3.IntegrityError):
        load_rows(conn, "exercise", SQUAT.replace('"barbell"', '"trap_bar"'))


def test_two_rows_with_one_id_are_refused() -> None:
    conn = open_store(":memory:")
    second = SQUAT.replace("A1B2C3D4", "E5F6A7B8")

    with pytest.raises(sqlite3.IntegrityError):
        load_rows(conn, "exercise", SQUAT + "\n" + second + "\n")
