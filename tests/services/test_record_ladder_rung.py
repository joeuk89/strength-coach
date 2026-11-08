from typing import cast

import pytest
from support.clock import FixedClock
from support.plans import SQUAT_LINE, a_squat_program
from support.program_drafts import a_ladder_line, a_rung, a_session

from coach.core.errors import Invalid
from coach.services.record import RecordResult, record
from coach.store import decisions
from coach.store.connection import Connection

PLANK_LADDER = a_ladder_line("plank", a_rung(), a_rung("side_plank"), a_rung("copenhagen_plank"))


def a_ladder_program() -> Connection:
    return a_squat_program(a_session("lower", SQUAT_LINE, PLANK_LADDER))


def run(conn: Connection, text: str) -> RecordResult:
    return record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def ladder_rung(rung: int, *, exercise: str = "plank", session: str = "lower") -> str:
    return (
        '[[decision]]\nkind = "ladder_rung"\n'
        f'session = "{session}"\nexercise = "{exercise}"\nrung = {rung}\n'
        'because = "progress"\ntext = "Two clean holds; the athlete said yes."\n'
    )


def in_force(conn: Connection) -> list[tuple[str, int]]:
    return [
        (str(row["id"]), cast(dict[str, int], row["params"])["rung"])
        for row in decisions.in_force(conn)
        if row["kind"] == "ladder_rung"
    ]


def test_a_ladder_rung_decision_is_written_on_its_line_with_because_progress() -> None:
    conn = a_ladder_program()

    result = run(conn, ladder_rung(2))

    [row] = decisions.in_force(conn)
    assert result.ids == {"decision": ["d-0001"]}
    assert (row["kind"], row["session_id"], row["exercise_id"]) == ("ladder_rung", "lower", "plank")
    assert (row["params"], row["until"], row["because"]) == ({"rung": 2}, None, "progress")


def test_a_later_ladder_rung_on_the_same_line_supersedes_the_earlier_one_moving_down_too() -> None:
    conn = a_ladder_program()
    run(conn, ladder_rung(3))

    run(conn, ladder_rung(2))

    assert in_force(conn) == [("d-0002", 2)]


@pytest.mark.parametrize("rung", [0, -1])
def test_a_rung_below_one_is_refused(rung: int) -> None:
    with pytest.raises(Invalid) as raised:
        run(a_ladder_program(), ladder_rung(rung))

    assert raised.value.code == "invalid_argument"
    assert "rung" in raised.value.message


def test_a_rung_past_the_ladders_length_is_refused() -> None:
    conn = a_ladder_program()

    with pytest.raises(Invalid) as raised:
        run(conn, ladder_rung(4))

    assert raised.value.code == "state_conflict"
    assert "3 rungs" in raised.value.message
    assert in_force(conn) == []


@pytest.mark.parametrize(
    ("exercise", "session"), [("bb_back_squat", "lower"), ("side_plank", "lower")]
)
def test_a_ladder_rung_on_a_line_that_is_no_exercise_ladder_key_is_refused(
    exercise: str, session: str
) -> None:
    with pytest.raises(Invalid) as raised:
        run(a_ladder_program(), ladder_rung(1, exercise=exercise, session=session))

    assert raised.value.code == "state_conflict"
