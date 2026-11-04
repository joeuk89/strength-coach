"""Which workouts the check-in reads as Activities: a matched workout by its session's kind, an
unmatched one by its content (docs/spec/week.md, "Match"; ADR 0010)."""

import datetime
from typing import Any, cast

from support.check_in_cards import opened
from support.closed_weeks import monday
from support.history import a_logged_workout
from support.plans import SQUAT_LINE, a_squat_program, an_approved_plan, squat_logged
from support.program_drafts import a_line, a_session

from coach.store.connection import Connection

HANG_TEMPLATE = "B9380898"
SWING_TEMPLATE = "F8A0FCCA"
HANGS = (HANG_TEMPLATE, ((None, 30, 8.0),) * 3)
HANG = a_line(
    "dead_hang", scheme={"name": "hold"}, start_load=None, sets=[{"count": 3, "duration_s": 30}]
)
PRACTICE = a_session("hang", HANG, kind="practice", tier="optional", cadence="daily")
LOWER = a_session("lower", SQUAT_LINE)
SWINGS = a_session(
    "cond-swings",
    a_line("kb_swing", scheme={"name": "hold"}, start_load=35, sets=[{"count": 1, "reps": 12}]),
    kind="conditioning",
    tier="optional",
    minutes=16,
    scheme={
        "name": "emom_density",
        "minutes": 12,
        "minutes_cap": 16,
        "minutes_step": 2,
        "reps": {"kb_swing": 12},
        "reps_cap": {"kb_swing": 15},
        "rpe_target": 8,
    },
)


def day(n: int) -> str:
    return (datetime.date.fromisoformat(monday(0)) + datetime.timedelta(days=n)).isoformat()


def activity_rows(conn: Connection) -> list[dict[str, Any]]:
    field = next((f for f in opened(conn).fields if f.name == "activities"), None)
    return [] if field is None else cast(list[dict[str, Any]], field.facts["rows"])


def activity_ids(conn: Connection) -> list[str]:
    return [r["id"] for r in activity_rows(conn)]


def a_lower_week() -> Connection:
    """`lower` on Monday, its week approved: Tuesday has no session to match."""
    conn = a_squat_program(LOWER)
    an_approved_plan(conn, monday(0))
    return conn


def test_a_week_of_daily_practice_hangs_yields_no_activity_and_no_cap() -> None:
    conn = a_squat_program(PRACTICE)
    an_approved_plan(conn, monday(0))
    for n in range(7):
        a_logged_workout(conn, f"h-{n}", day(n), HANGS)

    card = opened(conn)

    assert "activity_cap_exceeded" not in [w.code for w in card.warnings]
    assert activity_ids(conn) == []


def test_a_hangs_only_workout_matched_to_a_lifting_session_yields_no_activity() -> None:
    conn = a_lower_week()
    a_logged_workout(conn, "h-1", day(0), HANGS)

    assert activity_ids(conn) == []


def test_an_unrated_workout_matched_to_a_conditioning_session_is_a_quality_activity_at_7() -> None:
    conn = a_squat_program(LOWER, SWINGS)
    an_approved_plan(conn, monday(0))
    a_logged_workout(conn, "h-1", day(2), (SWING_TEMPLATE, ((24.0, 12, None),) * 12))

    assert activity_rows(conn) == [
        {
            "id": "h-1",
            "date": day(2),
            "kind": "conditioning",
            "minutes": None,
            "rpe": 7.0,
            "quality": True,
        }
    ]


def test_an_unmatched_hangs_only_workout_is_still_an_activity() -> None:
    conn = a_lower_week()
    a_logged_workout(conn, "h-1", day(1), (HANG_TEMPLATE, ((None, 30, 6.0),) * 3))

    assert activity_rows(conn) == [
        {
            "id": "h-1",
            "date": day(1),
            "kind": "conditioning",
            "minutes": None,
            "rpe": 6.0,
            "quality": False,
        }
    ]


def test_an_unmatched_workout_with_a_load_mode_set_yields_no_activity() -> None:
    conn = a_lower_week()
    a_logged_workout(conn, "h-1", day(1), HANGS, ("SQ-0001", ((60.0, 5, 7.0),)))
    squat_logged(conn, "h-2", day(3), (135, 5, 7))

    assert activity_ids(conn) == []
