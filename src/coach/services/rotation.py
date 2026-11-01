"""Which week a plan is drafted for and the rotation position it is planned against."""

import datetime

from coach.core.planned_week import RotationPosition, infer_position, week_monday
from coach.store import programs, week_plans
from coach.store.connection import Connection


def default_week(conn: Connection, today: datetime.date) -> datetime.date:
    """The first week from this one on with no approved WeekPlan (verbs.md, "Arguments with
    rules")."""
    approved = week_plans.approved_weeks(conn)
    monday = week_monday(today)
    while monday.isoformat() in approved:
        monday += datetime.timedelta(weeks=1)
    return monday


def rotation_position(
    conn: Connection, version: programs.VersionRow, monday: datetime.date
) -> RotationPosition:
    in_force = week_plans.in_force(conn, monday.isoformat())
    previous = week_plans.last_before(conn, monday.isoformat(), since=_block_monday(conn))
    return infer_position(
        version.form.schedule.rotation,
        adopted=version.position,
        previous=None if previous is None else str(previous["position"]),
        in_force=None if in_force is None else str(in_force["position"]),
    )


def _block_monday(conn: Connection) -> str | None:
    opened = programs.block_opened(conn)
    if opened is None:
        return None
    return week_monday(datetime.date.fromisoformat(opened)).isoformat()
