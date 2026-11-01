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
) -> dict[str, PlannedSession]:
    """Workout id to the planned session it took. A claim (a `match` Annotation, or a manual
    coach-led workout naming its session) is honoured first, inside the claimed session's window;
    every other workout takes, in date then start-time order, the session of its routine inside
    its window or else the first untaken candidate."""
    ordered = sorted(workouts, key=lambda w: (w.date, w.started, w.id))
    taken: set[int] = set()
    found: dict[str, PlannedSession] = {}
    for workout in ordered:
        claim = claims.get(workout.id)
        if claim is None:
            continue
        claimed_on, session_id = claim
        index = next(
            (
                i
                for i, s in enumerate(planned)
                if i not in taken and s.session_id == session_id and covers(s, claimed_on)
            ),
            None,
        )
        if index is not None:
            taken.add(index)
            found[workout.id] = planned[index]
    for workout in ordered:
        if workout.id in claims:
            continue
        candidates = [
            i for i, s in enumerate(planned) if i not in taken and covers(s, workout.date)
        ]
        own = [
            i
            for i in candidates
            if workout.routine_id is not None
            and routines.get(planned[i].session_id) == workout.routine_id
        ]
        if own or candidates:
            chosen = (own or candidates)[0]
            taken.add(chosen)
            found[workout.id] = planned[chosen]
    return found


def covers(session: PlannedSession, day: datetime.date) -> bool:
    if session.cadence == "standing":
        monday = week_monday(session.date)
        return monday <= day < monday + datetime.timedelta(days=DAYS_IN_WEEK)
    return day == session.date


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
