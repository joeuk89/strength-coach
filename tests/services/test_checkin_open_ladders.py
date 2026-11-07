import datetime
from typing import cast

from support.check_in_cards import field_of, opened
from support.clock import FixedClock, at
from support.history import a_logged_workout
from support.plans import SQUAT_LINE, a_squat_program
from support.program_drafts import a_ladder_line, a_rung, a_session

from coach.core.check_in_card import Ask
from coach.services.checkin_record import checkin_record
from coach.store.connection import Connection

FIRST_SUNDAY = datetime.date(2026, 11, 8)
TEMPLATES = {"dead_bug": "D8911FC4", "ab_wheel": "99D5F10E"}
CORE_LADDER = a_ladder_line(
    "dead_bug",
    a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}]),
    a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    a_rung("hanging_leg_raise", sets=[{"count": 3, "reps": 6, "rpe": 8}]),
)


def a_ladder_program(ladder: dict[str, object] = CORE_LADDER) -> Connection:
    """Adopted on 30 Oct 2026, the opening rung's start."""
    return a_squat_program(a_session("lower", SQUAT_LINE, ladder))


def logged(conn: Connection, exercise: str, on: str, reps: int) -> None:
    a_logged_workout(conn, f"h-{exercise}-{on}", on, (TEMPLATES[exercise], ((None, reps, 8),) * 3))


type Row = dict[str, object]


def ladder_rows(conn: Connection, on: datetime.date = FIRST_SUNDAY) -> list[Row]:
    return cast(list[Row], field_of(opened(conn, on), "ladders").facts["rows"])


def test_the_ladders_field_follows_lifts_with_the_standing_rung_and_its_exposure_count() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-08", 10)

    card = opened(conn)

    names = [f.name for f in card.fields]
    assert names[names.index("ladders") - 1 : names.index("ladders") + 1] == ["lifts", "ladders"]
    assert field_of(card, "ladders").facts["rows"] == [
        {
            "session": "lower",
            "line": "dead_bug",
            "rung": 1,
            "exercise": "dead_bug",
            "rungs": 3,
            "exposures": 1,
            "needed": 2,
            "met": False,
            "next": "ab_wheel",
        }
    ]
    assert field_of(card, "ladders").asks == ()


def test_a_met_rung_says_met_and_names_the_next_rung() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)

    [row] = ladder_rows(conn)

    assert (row["exposures"], row["met"], row["next"]) == (2, True, "ab_wheel")


def test_a_set_short_of_the_criterion_breaks_the_run_of_exposures() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 9)

    [row] = ladder_rows(conn)

    assert (row["exposures"], row["met"]) == (0, False)


def test_a_manual_rung_asks_whether_the_athlete_is_ready_for_the_next_rung() -> None:
    manual = a_ladder_line(
        "dead_bug",
        a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}], advance={"manual": True}),
        a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    )
    conn = a_ladder_program(manual)
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)

    ladders = field_of(opened(conn), "ladders")

    [row] = cast(list[Row], ladders.facts["rows"])
    assert (row["met"], row["needed"], row["next"]) == (False, None, "ab_wheel")
    assert ladders.asks == (Ask("ready_for_next_rung", "line:lower/dead_bug"),)


def test_a_card_with_no_ladder_line_drops_the_field() -> None:
    conn = a_squat_program()

    assert "ladders" not in [f.name for f in opened(conn).fields]


def test_a_ladder_rung_in_the_check_in_draft_moves_the_next_card_to_the_new_rung_at_zero() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)
    draft = (
        'date = 2026-11-08\ntier = "light"\nread = "Two clean weeks."\n'
        '[[decision]]\nkind = "ladder_rung"\nsession = "lower"\nexercise = "dead_bug"\n'
        'rung = 2\nbecause = "progress"\ntext = "Rung 1 met; the athlete said yes."\n'
    )
    checkin_record(conn, draft.encode(), file="c.toml", clock=FixedClock(at(FIRST_SUNDAY)))

    [row] = ladder_rows(conn, FIRST_SUNDAY + datetime.timedelta(days=7))

    assert row == {
        "session": "lower",
        "line": "dead_bug",
        "rung": 2,
        "exercise": "ab_wheel",
        "rungs": 3,
        "exposures": 0,
        "needed": 2,
        "met": False,
        "next": "hanging_leg_raise",
    }
