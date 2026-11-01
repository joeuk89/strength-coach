"""Step 4, the one cut per line (docs/spec/prescription.md, "The cut" and "The return band")."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from coach.core.load import Load
from coach.core.program.form import Deload, Number, Reps, SetGroup


@dataclass(frozen=True)
class Band:
    low: int
    high: int | None
    load_factor: float
    set_delta: int
    rpe_cap: Number
    rungs_back: int

    @property
    def label(self) -> str:
        return f"{self.low}+" if self.high is None else f"{self.low}–{self.high}"


RETURN_BANDS = (
    Band(11, 21, 0.95, 1, 8, 1),
    Band(22, 42, 0.90, 1, 8, 2),
    Band(43, None, 0.85, 1, 7, 3),
)
RETURN_BANDS_RN = "rn:detraining-return.3"


def return_band(days_off: int) -> Band | None:
    return next(
        (b for b in RETURN_BANDS if b.low <= days_off and (b.high is None or days_off <= b.high)),
        None,
    )


@dataclass(frozen=True)
class LightShape:
    set_cut_pct: Number
    load_cut_pct: Number
    rpe_cap: Number | None


def light_shape(deload: Deload | None, restated: Mapping[str, object]) -> LightShape:
    """The version's `[deload]` as the `light_week` override restates it for one week."""

    def field(name: str, default: Number | None) -> Number | None:
        value = restated.get(name, default if deload is None else getattr(deload, name))
        return value if isinstance(value, int | float) else default

    return LightShape(
        set_cut_pct=field("set_cut_pct", 0) or 0,
        load_cut_pct=field("load_cut_pct", 0) or 0,
        rpe_cap=field("rpe_cap", None),
    )


def cut_each_working_group(sets: Sequence[SetGroup], pct: Number) -> tuple[SetGroup, ...]:
    return tuple(
        replace(g, count=max(1, g.count - _round_half_up(g.count * pct / 100))) if g.working else g
        for g in sets
    )


def one_working_set_fewer(sets: Sequence[SetGroup]) -> tuple[SetGroup, ...]:
    """The set comes off the last working group with more than one set; with every working group
    a single, the last group goes. A line keeps at least one working set."""
    working = [i for i, g in enumerate(sets) if g.working]
    multiple = [i for i in working if sets[i].count > 1]
    if multiple:
        last = multiple[-1]
        return tuple(replace(g, count=g.count - 1) if i == last else g for i, g in enumerate(sets))
    if len(working) > 1:
        return tuple(g for i, g in enumerate(sets) if i != working[-1])
    return tuple(sets)


def close_rep_outs(sets: Sequence[SetGroup]) -> tuple[SetGroup, ...]:
    return tuple(replace(g, reps=_closed(g.reps)) if g.working else g for g in sets)


def working_set_count(sets: Sequence[SetGroup]) -> int:
    return sum(g.count for g in sets if g.working)


def rungs_back(rungs: Sequence[float], load: Load, count: int) -> Load:
    """`rungs` run from the most assistance down; a load between rungs sits on the rung with
    more assistance."""
    on = max((i for i, rung in enumerate(rungs) if rung >= load.amount), default=0)
    return replace(load, amount=rungs[max(0, on - count)])


def _closed(reps: Reps | None) -> Reps | None:
    return int(reps.rstrip("+")) if isinstance(reps, str) else reps


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)
