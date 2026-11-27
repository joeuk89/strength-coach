"""Whether the WeekPlan in force this week predates the Program version in force."""

import datetime

from coach.core.flag import Flag
from coach.core.plan_behind import ApprovedPlan, plan_behind_program
from coach.core.planned_week import week_monday
from coach.store import programs, week_plans
from coach.store.connection import Connection


def plan_behind(
    conn: Connection, today: datetime.date, *, version_id: str | None = None
) -> tuple[Flag, ...]:
    """`version_id` names the version in force, by default the latest; an adopt's dry run passes
    the one it would record."""
    monday = week_monday(today)
    plan = _approved(conn, monday)
    if plan is None:
        return ()
    if version_id is None:
        latest = programs.latest(conn)
        version_id = latest.id if latest else None
    next_week = _approved(conn, monday + datetime.timedelta(days=7))
    return plan_behind_program(plan, version_id, next_week=next_week)


def _approved(conn: Connection, monday: datetime.date) -> ApprovedPlan | None:
    row = week_plans.in_force(conn, monday.isoformat())
    if row is None:
        return None
    under = programs.in_force_at(conn, str(row["approved_at"]))
    return ApprovedPlan(str(row["id"]), monday, under.id if under else None)
