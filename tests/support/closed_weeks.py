"""Scenario builders for closed weeks: an approved squat week with its frozen prescription, the
workout that trained it and the Check-in row whose window closes it. Each writes only through
`store` functions."""

import datetime

from coach.store import rows
from coach.store.connection import Connection
from support.plans import a_frozen_prescription, an_approved_plan, squat_logged

FIRST_MONDAY = datetime.date(2026, 11, 2)
SQUAT_WORKING = {"type": "working", "count": 4, "range": [6, 8], "rpe": 8}


def monday(n: int) -> str:
    return (FIRST_MONDAY + datetime.timedelta(weeks=n)).isoformat()


def a_planned_squat_week(conn: Connection, week: str) -> str:
    """The squat program's week approved: `lower` on the Monday, 4×6–8 @8."""
    plan_id = an_approved_plan(conn, week)
    a_frozen_prescription(
        conn, plan_id, "lower", week, "bb_back_squat", set_groups=[SQUAT_WORKING], change="held"
    )
    return plan_id


def a_hard_squat_week(conn: Connection, week: str) -> str:
    plan_id = a_planned_squat_week(conn, week)
    squat_logged(conn, f"h-{week}", week, *[(120, 8, 8)] * 4)
    return plan_id


def a_check_in(
    conn: Connection, start: str, end: str, *, readiness: str | None = None, tier: str = "light"
) -> None:
    with conn:
        rows.insert(
            conn,
            "check_in",
            {
                "id": f"ci-{end}",
                "date": end,
                "tier": tier,
                "window_start": start,
                "window_end": end,
                "read": "A steady block.",
                "readiness": readiness,
                "status": "current",
                "draft_hash": f"sha256:{end}",
                "recorded_at": f"{end}T20:00:00+00:00",
            },
        )


def closed_through(conn: Connection, weeks: int) -> None:
    """One Check-in whose window covers the first `weeks` weeks."""
    last_sunday = FIRST_MONDAY + datetime.timedelta(weeks=weeks, days=-1)
    a_check_in(conn, FIRST_MONDAY.isoformat(), last_sunday.isoformat())
