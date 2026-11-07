"""Days off per lift (docs/spec/prescription.md, "The anchor exposure")."""

import datetime
import itertools
import math
import statistics
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from coach.core.exposure import Exposure

GAPS_READ = 4
USUAL_INTERVAL_DAYS = (7, 14)
USUAL_INTERVAL_DAYS_RN = None
GRACE_DAYS = 10
GRACE_DAYS_RN = "rn:detraining-return.3"


@dataclass(frozen=True)
class DaysOff:
    days: int
    layoff: int
    exposure_age: int
    usual_interval: int

    @property
    def decayed(self) -> bool:
        return self.days > GRACE_DAYS


def days_off(
    on: datetime.date,
    *,
    line_dates: Iterable[datetime.date],
    lifting_dates: Iterable[datetime.date],
) -> DaysOff:
    """`line_dates` are the lift's exposure dates and its session's trained-unlogged dates;
    `lifting_dates` every lifting exposure date of any kind. A missing term counts zero."""
    line = sorted({d for d in line_dates if d < on})
    lifting = [d for d in lifting_dates if d < on]
    layoff = (on - max(lifting)).days if lifting else 0
    exposure_age = (on - line[-1]).days if line else 0
    interval = usual_interval(line)
    days = max(layoff, exposure_age - interval if line else 0)
    return DaysOff(days, layoff, exposure_age, interval)


def usual_interval(dates: Iterable[datetime.date]) -> int:
    """The median of the last four gaps in whole days, rounded down and clamped."""
    ordered = sorted(set(dates))
    gaps = [(b - a).days for a, b in itertools.pairwise(ordered)][-GAPS_READ:]
    low, high = USUAL_INTERVAL_DAYS
    if not gaps:
        return low
    return min(max(math.floor(statistics.median(gaps)), low), high)


@dataclass(frozen=True)
class SessionTrained:
    """A trained-unlogged Annotation or a hand-entered Workout with no sets: a lifting exposure
    date for every line of its session, carrying no load."""

    date: datetime.date
    session_id: str | None


def line_days_off(
    exposures: Iterable[Exposure],
    trained: Iterable[SessionTrained],
    *,
    exercise_id: str,
    session_id: str,
    on: datetime.date,
    rungs: Collection[str] = (),
) -> DaysOff:
    """`rungs` are a ladder line's rung exercises: an exposure of any of them trains the line."""
    exposures = tuple(exposures)
    trained = tuple(trained)
    session_dates = [t.date for t in trained if t.session_id == session_id]
    return days_off(
        on,
        line_dates=[
            *(e.date for e in exposures if e.exercise_id == exercise_id or e.exercise_id in rungs),
            *session_dates,
        ],
        lifting_dates=[*(e.date for e in exposures), *(t.date for t in trained)],
    )
