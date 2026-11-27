"""Match: the link from a workout to the planned session it fulfilled (docs/spec/week.md,
"Match"), and what an unmatched workout is."""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from coach.core.exposure import Exposure, LibraryEntry
from coach.core.log import StoredSet
from coach.core.planned_week import DAYS_IN_WEEK, week_monday
from coach.core.prescription import PlannedSession

type WorkoutClass = Literal["lifting", "conditioning", "unmapped"]
type PlannedRef = tuple[datetime.date, str]

CONDITIONING_MODES = ("duration", "distance")
# An unrated conditioning workout's RPE, and the RPE a quality bout reaches (rn:running-load.6).
DEFAULT_SESSION_RPE = 7.0
QUALITY_RPE = 7.0
# A session of these kinds takes a workout only by its routine or a shared exercise.
LINE_BOUND_KINDS = ("conditioning", "practice")


@dataclass(frozen=True)
class WeekWorkout:
    id: str
    date: datetime.date
    exposures: tuple[Exposure, ...] = ()
    routine_id: str | None = None
    started: str = ""
    kind: WorkoutClass = "lifting"
    minutes: int | None = None
    session_rpe: float | None = None


def in_start_order(workouts: Iterable[WeekWorkout]) -> tuple[WeekWorkout, ...]:
    return tuple(sorted(workouts, key=lambda w: (w.date, w.started, w.id)))


@dataclass(frozen=True)
class Activity:
    date: datetime.date
    minutes: int | None
    rpe: float
    quality: bool


def match_week(
    planned: Sequence[PlannedSession],
    workouts: Iterable[WeekWorkout],
    *,
    routines: Mapping[str, str],
    claims: Mapping[str, PlannedRef],
    lines: Mapping[PlannedRef, frozenset[str]],
) -> dict[str, PlannedSession]:
    """Workout id to the planned session it took; a session may hold several workouts. A claim
    (a `match` Annotation, or a manual coach-led workout naming its session) is honoured first,
    inside the claimed session's window. Every other workout, in date then start-time order,
    takes the unmatched session of its routine inside its window, else joins a matched session
    holding a workout on its date that it shares a routine or a line with, else takes the
    unmatched candidate with the narrowest window. `lines` holds each session's line
    exercises, authored and frozen."""
    return _Matcher(planned, routines, lines).run(in_start_order(workouts), claims)


@dataclass
class _Matcher:
    planned: Sequence[PlannedSession]
    routines: Mapping[str, str]
    lines: Mapping[PlannedRef, frozenset[str]]

    def run(
        self, ordered: Sequence[WeekWorkout], claims: Mapping[str, PlannedRef]
    ) -> dict[str, PlannedSession]:
        held: dict[int, set[datetime.date]] = {}
        found: dict[str, PlannedSession] = {}
        for workout in ordered:
            claim = claims.get(workout.id)
            if claim is None:
                continue
            claimed_on, session_id = claim
            index = next(
                (
                    i
                    for i, s in enumerate(self.planned)
                    if s.session_id == session_id and covers(s, claimed_on)
                ),
                None,
            )
            if index is not None:
                held.setdefault(index, set()).add(workout.date)
                found[workout.id] = self.planned[index]
        for workout in ordered:
            if workout.id in claims:
                continue
            chosen = self._choose(workout, held)
            if chosen is not None:
                held.setdefault(chosen, set()).add(workout.date)
                found[workout.id] = self.planned[chosen]
        return found

    def _choose(self, workout: WeekWorkout, held: Mapping[int, set[datetime.date]]) -> int | None:
        covering = [i for i, s in enumerate(self.planned) if covers(s, workout.date)]
        open_ = [i for i in covering if i not in held]
        own = [i for i in open_ if self._own(workout, i)]
        if own:
            return own[0]
        joined = [
            i
            for i in covering
            if workout.date in held.get(i, ())
            and (self._own(workout, i) or self._shared(workout, i))
        ]
        if joined:
            return min(joined, key=lambda i: (not self._own(workout, i), -self._shared(workout, i)))
        candidates = [
            i
            for i in open_
            if self.planned[i].kind not in LINE_BOUND_KINDS or self._shared(workout, i)
        ]
        if candidates:
            return min(candidates, key=lambda i: window_days(self.planned[i]))
        return None

    def _own(self, workout: WeekWorkout, index: int) -> bool:
        return (
            workout.routine_id is not None
            and self.routines.get(self.planned[index].session_id) == workout.routine_id
        )

    def _shared(self, workout: WeekWorkout, index: int) -> int:
        session = self.planned[index]
        logged = {e.exercise_id for e in workout.exposures}
        return len(logged & self.lines.get((session.date, session.session_id), frozenset()))


def window(session: PlannedSession) -> tuple[datetime.date, datetime.date]:
    """The first and last day a workout can match the session on (week.md, "Match")."""
    if session.cadence == "standing":
        monday = week_monday(session.date)
        return monday, monday + datetime.timedelta(days=DAYS_IN_WEEK - 1)
    return session.date, session.date


def covers(session: PlannedSession, day: datetime.date) -> bool:
    first, last = window(session)
    return first <= day <= last


def window_days(session: PlannedSession) -> int:
    first, last = window(session)
    return (last - first).days + 1


def workout_class(sets: Iterable[StoredSet], library: Mapping[str, LibraryEntry]) -> WorkoutClass:
    modes = [
        library[s.hevy_template_id].load_mode
        for s in sets
        if s.hevy_template_id is not None and s.hevy_template_id in library
    ]
    if not modes:
        return "unmapped"
    if all(mode in CONDITIONING_MODES for mode in modes):
        return "conditioning"
    return "lifting"


def conditioning_activity(
    on: datetime.date, minutes: int | None, logged_rpe: Sequence[float]
) -> Activity:
    rpe = sum(logged_rpe) / len(logged_rpe) if logged_rpe else DEFAULT_SESSION_RPE
    return Activity(on, minutes, rpe, rpe >= QUALITY_RPE)
