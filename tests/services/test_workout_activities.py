"""Which workouts the check-in reads as Activities: a matched workout by its session's kind, an
unmatched one by its content (docs/spec/week.md, "Match"; ADR 0010)."""

import datetime
from typing import Any, cast

from support.check_in_cards import opened
from support.closed_weeks import monday
from support.history import a_logged_workout
from support.plans import a_squat_program, an_approved_plan
from support.program_drafts import a_line, a_session

from coach.store.connection import Connection

HANG_TEMPLATE = "B9380898"
HANG = a_line(
    "dead_hang", scheme={"name": "hold"}, start_load=None, sets=[{"count": 3, "duration_s": 30}]
)
PRACTICE = a_session("hang", HANG, kind="practice", tier="optional", cadence="daily")


def day(n: int) -> str:
    return (datetime.date.fromisoformat(monday(0)) + datetime.timedelta(days=n)).isoformat()


def activity_ids(conn: Connection) -> list[str]:
    field = next((f for f in opened(conn).fields if f.name == "activities"), None)
    rows = [] if field is None else cast(list[dict[str, Any]], field.facts["rows"])
    return [r["id"] for r in rows]


def test_a_week_of_daily_practice_hangs_yields_no_activity_and_no_cap() -> None:
    conn = a_squat_program(PRACTICE)
    an_approved_plan(conn, monday(0))
    for n in range(7):
        a_logged_workout(conn, f"h-{n}", day(n), (HANG_TEMPLATE, ((None, 30, 8.0),) * 3))

    card = opened(conn)

    assert "activity_cap_exceeded" not in [w.code for w in card.warnings]
    assert activity_ids(conn) == []
