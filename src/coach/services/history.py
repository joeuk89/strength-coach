"""The logged history as core values: exposures and the session dates trained without sets. A
workout matched to a conditioning session yields no Exposures (ADR 0010)."""

import datetime
from dataclasses import dataclass
from typing import cast

from coach.core.config import Units
from coach.core.days_off import DaysOff, SessionTrained, line_days_off
from coach.core.exposure import Exposure, LoggedWorkout, Matched, resolve
from coach.core.planned_week import week_monday
from coach.services.closed_weeks import WeekLog, trained_without_sets
from coach.store import annotations, exercises, week_plans, workouts
from coach.store.connection import Connection


@dataclass(frozen=True)
class History:
    exposures: tuple[Exposure, ...]
    trained: tuple[SessionTrained, ...]


def read_history(conn: Connection, units: Units) -> History:
    sessions = workouts.sessions_of_current(conn)
    current = workouts.current_workouts(conn)
    live = annotations.live(conn)
    conditioning = WeekLog(conn, units).conditioning
    logged = [
        LoggedWorkout(v.id, _day(v.date), v.sets, _match(conn, sessions.get(v.id), _day(v.date)))
        for v in current
        if v.id not in conditioning
    ]
    exposures = resolve(logged, exercises.library(conn), live, units)
    return History(exposures, trained_without_sets(live, current, sessions))


def days_off_for_line(
    conn: Connection, *, exercise_id: str, session_id: str, on: datetime.date, units: Units
) -> DaysOff:
    history = read_history(conn, units)
    return line_days_off(
        history.exposures,
        history.trained,
        exercise_id=exercise_id,
        session_id=session_id,
        on=on,
    )


def _match(conn: Connection, session_id: str | None, on: datetime.date) -> Matched | None:
    """The Match seam: a manual coach-led workout names its session; nothing here derives a
    Hevy workout's Match. The plan in force on the date tells a light week and the lines that
    took the return band in it (prescription.md, "The anchor exposure")."""
    if session_id is None:
        return None
    plan = week_plans.in_force(conn, week_monday(on).isoformat())
    if plan is None:
        return Matched(session_id)
    plan_id = str(plan["id"])
    light = any(row["kind"] == "light_week" for row in week_plans.overrides(conn, plan_id))
    returned = frozenset(
        str(row["exercise_id"])
        for row in week_plans.prescriptions(conn, plan_id)
        if row["session_id"] == session_id and _took_return_band(row["steps"])
    )
    return Matched(session_id, light, returned)


def _took_return_band(steps: object) -> bool:
    return any(
        str(step.get("cause", "")).startswith("return")
        for step in cast(list[dict[str, object]], steps)
    )


def _day(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)
