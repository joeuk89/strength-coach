"""The pieces of the block-boundary report that are arithmetic (docs/spec/goals.md, "`coach
progress`" and "Milestone")."""

import datetime
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from coach.core.config import Units
from coach.core.e1rm import point
from coach.core.exposure import Exposure, ExposureSet
from coach.core.goal import Milestone
from coach.core.phase_trend import AVERAGE_DAYS, WeighIns, fourteen_day_average
from coach.core.units import from_kg

# Two weigh-ins in the 14 days is the engine's opinion (goals.md, "Milestone").
WEIGH_INS_FOR_A_MULTIPLE = 2
PRECISION = 2

type Measure = Callable[[Exposure], float | None]


@dataclass(frozen=True)
class MilestoneRead:
    """`to_go` is what remains (load, reps or multiple) while unreached and computable."""

    milestone: Milestone
    reached: datetime.date | None
    to_go: dict[str, float] | None = None
    computable: bool = True


@dataclass(frozen=True)
class BestSet:
    date: datetime.date
    load: float | None
    reps: int


def milestone_read(
    milestone: Milestone, exposures: Iterable[Exposure], weigh_ins: WeighIns, units: Units
) -> MilestoneRead:
    """Reached by the first Exposure meeting the target; never stored."""
    history = sorted(
        (e for e in exposures if e.exercise_id == milestone.exercise), key=lambda e: e.date
    )
    target = milestone.target
    if target.kind == "load_x_reps":
        assert target.load is not None and target.reps is not None
        return _load_x_reps(milestone, history, target.load, target.reps)
    assert target.value is not None
    if target.kind == "e1rm":
        return _reached_by(milestone, history, target.value, best_e1rm, "load")
    return _bodyweight_multiple(milestone, history, target.value, weigh_ins, units)


def best_set(exposures: Iterable[Exposure], exercise_id: str) -> BestSet | None:
    """The heaviest working set, then the most reps at it; under assistance, the least."""
    found = [
        (exposure.date, logged)
        for exposure in exposures
        if exposure.exercise_id == exercise_id
        for logged in exposure.working
        if logged.reps
    ]
    if not found:
        return None
    day, logged = max(found, key=lambda pair: (_heaviness(pair[1]), pair[1].reps or 0))
    return BestSet(day, None if logged.load is None else logged.load.amount, logged.reps or 0)


def best_e1rm(exposure: Exposure) -> float | None:
    points = [found.load.amount for s in exposure.working if (found := point(exposure, s))]
    return max(points, default=None)


def _load_x_reps(
    milestone: Milestone, history: Sequence[Exposure], load: float, reps: int
) -> MilestoneRead:
    sets = [(e.date, s) for e in history for s in e.working if s.reps is not None]
    for day, logged in sets:
        if _load(logged) >= load and (logged.reps or 0) >= reps:
            return MilestoneRead(milestone, day)
    at_load = [s.reps or 0 for _, s in sets if _load(s) >= load]
    if at_load:
        return MilestoneRead(milestone, None, {"reps": reps - max(at_load)})
    at_reps = [_load(s) for _, s in sets if (s.reps or 0) >= reps]
    return MilestoneRead(
        milestone, None, {"load": round(load - max(at_reps, default=0), PRECISION)}
    )


def _reached_by(
    milestone: Milestone,
    history: Sequence[Exposure],
    target: float,
    measure: Measure,
    unit: str,
) -> MilestoneRead:
    measured = [(e.date, m) for e in history if (m := measure(e)) is not None]
    reached = next((day for day, m in measured if m >= target), None)
    if reached is not None:
        return MilestoneRead(milestone, reached)
    best = max((m for _, m in measured), default=0)
    return MilestoneRead(milestone, None, {unit: round(target - best, PRECISION)})


def _bodyweight_multiple(
    milestone: Milestone,
    history: Sequence[Exposure],
    target: float,
    weigh_ins: WeighIns,
    units: Units,
) -> MilestoneRead:
    def multiple(exposure: Exposure) -> float | None:
        e1rm = best_e1rm(exposure)
        if e1rm is None or _weigh_ins_before(weigh_ins, exposure.date) < WEIGH_INS_FOR_A_MULTIPLE:
            return None
        average = fourteen_day_average(weigh_ins, exposure.date)
        assert average is not None
        return round(e1rm / from_kg(average, units), PRECISION)

    read = _reached_by(milestone, history, target, multiple, "multiple")
    if read.reached is None and (not history or multiple(history[-1]) is None):
        return MilestoneRead(milestone, None, None, computable=False)
    return read


def _weigh_ins_before(weigh_ins: WeighIns, on: datetime.date) -> int:
    start = on - datetime.timedelta(days=AVERAGE_DAYS - 1)
    return sum(1 for day in weigh_ins if start <= day <= on)


def _load(logged: ExposureSet) -> float:
    """An unloaded bodyweight set counts as load 0."""
    return 0 if logged.load is None else logged.load.amount


def _heaviness(logged: ExposureSet) -> float:
    if logged.load is None:
        return 0
    return -logged.load.amount if logged.load.mode == "assisted" else logged.load.amount
