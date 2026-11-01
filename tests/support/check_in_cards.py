"""Scenario builders for `checkin open`: a two-session squat and bench program with its first
week approved, and the call that opens the card at a date."""

import datetime

from coach.core.check_in_card import Card, CardField
from coach.services.checkin_open import checkin_open
from coach.store.connection import Connection
from support.clock import FixedClock
from support.closed_weeks import a_planned_squat_week, monday
from support.plans import SQUAT_LINE, a_frozen_prescription, a_squat_program
from support.program_drafts import a_line, a_session

FIRST_SUNDAY = datetime.date(2026, 11, 8)
BENCH_WORKING = {"type": "working", "count": 3, "range": [6, 8], "rpe": 8}


def a_two_session_program() -> Connection:
    """`lower` (back squat) on Monday and `push` (bench press) on Wednesday."""
    return a_squat_program(
        a_session("lower", SQUAT_LINE), a_session("push", a_line("bb_bench_press"))
    )


def a_planned_two_session_week(conn: Connection, week: str) -> str:
    plan_id = a_planned_squat_week(conn, week)
    wednesday = (datetime.date.fromisoformat(week) + datetime.timedelta(days=2)).isoformat()
    a_frozen_prescription(
        conn,
        plan_id,
        "push",
        wednesday,
        "bb_bench_press",
        set_groups=[BENCH_WORKING],
        change="held",
    )
    return plan_id


def opened(conn: Connection, on: datetime.date = FIRST_SUNDAY, *, tier: str | None = None) -> Card:
    return checkin_open(conn, FixedClock(), date=on, tier=tier, units="lb")


def field_of(card: Card, name: str) -> CardField:
    return next(f for f in card.fields if f.name == name)


__all__ = ["monday"]
