"""The logged history as core values: exposures and the session dates trained without sets."""

import datetime
from dataclasses import dataclass

from coach.core.config import Units
from coach.core.days_off import DaysOff, SessionTrained, line_days_off
from coach.core.exposure import Annotation, Exposure, LoggedWorkout, Matched, resolve
from coach.core.log import WorkoutVersion
from coach.core.ref import Ref
from coach.store import annotations, exercises, week_plans, workouts
from coach.store.connection import Connection


@dataclass(frozen=True)
class History:
    exposures: tuple[Exposure, ...]
    trained: tuple[SessionTrained, ...]


def read_history(conn: Connection, units: Units) -> History:
    sessions = workouts.sessions_of_current(conn)
    light = week_plans.light_weeks(conn)
    current = workouts.current_workouts(conn)
    live = annotations.live(conn)
    logged = [
        LoggedWorkout(v.id, _day(v.date), v.sets, _match(sessions.get(v.id), _day(v.date), light))
        for v in current
    ]
    exposures = resolve(logged, exercises.library(conn), live, units)
    return History(exposures, (*_trained_unlogged(live), *_without_sets(current, sessions)))


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


def _match(
    session_id: str | None,
    on: datetime.date,
    light: tuple[tuple[datetime.date, datetime.date], ...],
) -> Matched | None:
    """The Match seam: a manual coach-led workout names its session; nothing here derives a
    Hevy workout's Match."""
    if session_id is None:
        return None
    return Matched(session_id, any(start <= on <= end for start, end in light))


def _trained_unlogged(live: tuple[Annotation, ...]) -> list[SessionTrained]:
    found: list[SessionTrained] = []
    for annotation in live:
        if annotation.kind == "trained_unlogged":
            day, _, session_id = Ref.parse(annotation.target).id.partition("/")
            found.append(SessionTrained(_day(day), session_id))
    return found


def _without_sets(
    current: tuple[WorkoutVersion, ...], sessions: dict[str, str]
) -> list[SessionTrained]:
    return [
        SessionTrained(_day(v.date), sessions.get(v.id))
        for v in current
        if v.source == "manual" and not v.sets
    ]


def _day(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)
