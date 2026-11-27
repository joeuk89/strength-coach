import datetime
from collections.abc import Sequence
from typing import cast

from support.check_in_cards import field_of, opened
from support.closed_weeks import a_planned_squat_week, monday
from support.plans import (
    a_frozen_prescription,
    a_squat_program,
    an_approved_plan,
    squat_logged,
)
from support.program_drafts import a_line, a_session

from coach.core.check_in_card import Ask
from coach.store.connection import Connection

THURSDAY = (datetime.date.fromisoformat(monday(0)) + datetime.timedelta(days=3)).isoformat()

TOP_BACKOFF = a_line(
    "bb_back_squat",
    sets=[{"count": 1, "reps": 5, "rpe": 8}, {"count": 3, "reps": 5, "rpe": 7}],
    scheme={"name": "top_backoff", "pct_of_top": 85},
    start_load=100,
)
TOP_BACKOFF_FROZEN = [
    {"type": "working", "count": 1, "reps": 5, "rpe": 8, "load": 225},
    {"type": "working", "count": 3, "reps": 5, "rpe": 7, "load": 190},
]


def a_top_backoff_week() -> Connection:
    """`lower` on Monday: the squat's top set of 5 at RPE 8 and 225 lb, three back-offs of 5 at
    RPE 7 and 190 lb."""
    conn = a_squat_program(a_session("lower", TOP_BACKOFF))
    plan_id = an_approved_plan(conn, monday(0))
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        monday(0),
        "bb_back_squat",
        set_groups=TOP_BACKOFF_FROZEN,
        change="derived",
    )
    return conn


def sets(*logged: tuple[float, int, float | None]) -> list[dict[str, object]]:
    return [{"load": load, "reps": reps, "rpe": rpe} for load, reps, rpe in logged]


def prescribed(*groups: tuple[int, int, float, float | None]) -> list[dict[str, object]]:
    return [
        {"reps": reps, "reps_top": top, "rpe": rpe, "load": load} for reps, top, rpe, load in groups
    ]


def lift_asks(conn: Connection) -> Sequence[Ask]:
    return [a for a in field_of(opened(conn), "lifts").asks if a.kind != "soreness_and_niggles"]


def test_a_week_logged_with_an_rpe_on_every_set_asks_only_soreness_and_niggles() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)

    lifts = field_of(opened(conn), "lifts")

    assert lifts.asks == (Ask("soreness_and_niggles"),)


def test_a_top_set_logged_with_no_rpe_asks_once_quoting_the_sets_and_the_prescription() -> None:
    conn = a_top_backoff_week()
    squat_logged(conn, "h-1", monday(0), (225, 5, None), *[(190, 5, 7)] * 3)

    assert lift_asks(conn) == [
        Ask(
            "lift_doubt",
            "exercise:bb_back_squat",
            reason="rpe_missing",
            params={
                "exposures": [
                    {
                        "session": "lower",
                        "date": monday(0),
                        "logged": sets((225, 5, None), *[(190, 5, 7)] * 3),
                        "prescribed": prescribed((5, 5, 8, 225), *[(5, 5, 7, 190)] * 3),
                    }
                ]
            },
        )
    ]


def test_a_back_off_logged_with_no_rpe_asks_nothing_as_the_scheme_reads_only_the_top_set() -> None:
    conn = a_top_backoff_week()
    squat_logged(conn, "h-1", monday(0), (225, 5, 8), (190, 5, None), *[(190, 5, 7)] * 2)

    assert lift_asks(conn) == []


def test_two_exposures_far_apart_at_similar_effort_ask_once_quoting_both() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(176, 5, 8)] * 4)
    squat_logged(conn, "h-2", THURSDAY, *[(110, 5, 6)] * 4)

    assert lift_asks(conn) == [
        Ask(
            "lift_doubt",
            "exercise:bb_back_squat",
            reason="exposures_disagree",
            params={
                "exposures": [
                    {
                        "session": "lower",
                        "date": monday(0),
                        "logged": sets(*[(176, 5, 8)] * 4),
                        "prescribed": prescribed(*[(6, 8, 8, None)] * 4),
                        "e1rm": 217.07,
                    },
                    {
                        "session": None,
                        "date": THURSDAY,
                        "logged": sets(*[(110, 5, 6)] * 4),
                        "prescribed": [],
                        "e1rm": 143.0,
                    },
                ]
            },
        )
    ]


def test_a_light_day_at_a_matching_lower_effort_raises_no_doubt() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(176, 6, 8)] * 4)
    squat_logged(conn, "h-2", THURSDAY, *[(150, 6, 6)] * 4)

    assert lift_asks(conn) == []


def test_reps_short_of_the_range_at_a_low_rpe_ask_once_for_that_lift() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 4, 6)] * 4)

    assert [(a.kind, a.reason) for a in lift_asks(conn)] == [
        ("lift_doubt", "reps_short_at_low_rpe")
    ]


def test_reps_short_of_the_range_at_the_authored_rpe_raise_no_doubt() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 5, 8)] * 4)

    assert lift_asks(conn) == []


def squat_row(conn: Connection) -> dict[str, object]:
    rows = cast(list[dict[str, object]], field_of(opened(conn), "lifts").facts["rows"])
    return next(r for r in rows if r["exercise"] == "bb_back_squat")


def test_a_lift_logged_one_and_a_half_under_its_authored_rpe_is_stated_and_not_asked() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 6.5)] * 4)

    assert lift_asks(conn) == []
    assert squat_row(conn)["under_authored_rpe"] == [
        {"session": "lower", "date": monday(0), "rpe_gap": -1.5}
    ]


def test_a_lift_logged_just_inside_its_authored_rpe_states_nothing() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 7)] * 4)

    assert "under_authored_rpe" not in squat_row(conn)


def test_a_line_a_return_band_capped_reads_no_rpe_gap() -> None:
    conn = a_squat_program()
    plan_id = an_approved_plan(conn, monday(0))
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        monday(0),
        "bb_back_squat",
        set_groups=[{"type": "working", "count": 4, "range": [6, 8], "rpe": 8, "rpe_cap": 6}],
        change="derived",
        steps=[{"cause": "return_band", "value": 0.8}],
    )
    squat_logged(conn, "h-1", monday(0), *[(100, 5, 6)] * 4)

    assert lift_asks(conn) == []
    assert "under_authored_rpe" not in squat_row(conn)
