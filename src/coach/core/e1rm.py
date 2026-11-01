"""e1RM (docs/spec/prescription.md, "The anchor exposure"): Epley on reps to failure."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass

from coach.core.exposure import Exposure, ExposureSet
from coach.core.load import Load, LoadMode
from coach.core.rack import Rack, round_to_rack

WINDOW_DAYS = 42
WINDOW_DAYS_RN = None
MAX_REPS_TO_FAILURE = 12
MAX_REPS_TO_FAILURE_RN = "rn:autoregulation.5"
LOAD_BEARING: frozenset[LoadMode] = frozenset({"total", "per_hand_x2", "single_implement"})
PRECISION = 2


@dataclass(frozen=True)
class E1rm:
    load: Load
    lower_bound: bool
    exposure: str


def reps_to_failure(reps: int, rpe: float | None) -> float:
    """With no RPE every rep counts as taken to failure, so the estimate is a lower bound."""
    return reps if rpe is None else reps + 10 - rpe


def point(exposure: Exposure, logged: ExposureSet) -> E1rm | None:
    """The set's e1RM when it qualifies."""
    if not _estimable(logged):
        return None
    assert logged.load is not None and logged.reps is not None
    to_failure = reps_to_failure(logged.reps, logged.rpe)
    if to_failure > MAX_REPS_TO_FAILURE:
        return None
    amount = round(logged.load.amount * (1 + to_failure / 30), PRECISION)
    return E1rm(Load(amount, logged.load.mode), logged.rpe is None, exposure.ref)


def e1rm(exposures: Iterable[Exposure], exercise_id: str, on: datetime.date) -> E1rm | None:
    """The best qualifying point in the window before `on`, exercise-wide. A newer set too far
    from failure at or above a point's load invalidates that point."""
    start = on - datetime.timedelta(days=WINDOW_DAYS)
    window = [e for e in exposures if e.exercise_id == exercise_id and start <= e.date < on]
    points: list[tuple[datetime.date, E1rm, float]] = []
    too_easy: list[tuple[datetime.date, float]] = []
    for exposure in window:
        for logged in exposure.working:
            if not _estimable(logged):
                continue
            assert logged.load is not None
            found = point(exposure, logged)
            if found is None:
                too_easy.append((exposure.date, logged.load.amount))
            else:
                points.append((exposure.date, found, logged.load.amount))
    standing = [
        found
        for day, found, load in points
        if not any(later > day and heavier >= load for later, heavier in too_easy)
    ]
    return max(standing, key=lambda found: found.load.amount, default=None)


def load_for(e1rm: Load, reps: int, rpe: float, rack: Rack) -> Load:
    """The load the model gives for `reps` at `rpe`, rounded down to a rack row."""
    target = round(e1rm.amount / (1 + reps_to_failure(reps, rpe) / 30), PRECISION)
    return round_to_rack(rack, Load(target, e1rm.mode), "cut").load


def _estimable(logged: ExposureSet) -> bool:
    return (
        logged.load is not None
        and logged.load.mode in LOAD_BEARING
        and logged.reps is not None
        and logged.reps > 0
    )
