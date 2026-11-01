"""`wave_531` (docs/spec/prescription.md, "The move, per scheme"): the registry's waves of the
training max, picked by the Block's hard-week count, the last working set open. The rule never
moves the training max."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.exposure import Exposure
from coach.core.line_history import top_on_grid
from coach.core.load import Load, LoadMode
from coach.core.prescription import DecisionInForce
from coach.core.rack import Rack, round_to_rack
from coach.core.registries.schemes import SCHEMES

_HOLDS = SCHEMES.get("wave_531").holds
WAVES = cast(list[list[int]], _HOLDS["waves"])
REP_OUTS = cast(list[str], _HOLDS["reps"])
PRECISION = 4


@dataclass(frozen=True)
class TrainingMax:
    load: Load
    source: str


def training_max(
    decisions: Iterable[DecisionInForce],
    exercise_id: str,
    start_load: float | None,
    mode: LoadMode,
) -> TrainingMax | None:
    """The `training_max` Decision in force on the exercise, else the line's start load."""
    for decision in reversed(tuple(decisions)):
        load = decision.params.get("load")
        if (
            decision.kind == "training_max"
            and decision.exercise_id == exercise_id
            and isinstance(load, int | float)
        ):
            return TrainingMax(Load(float(load), mode), decision.id)
    if start_load is None:
        return None
    return TrainingMax(Load(start_load, mode), "start_load")


def wave_index(hard_week_count: int) -> int:
    return hard_week_count % len(WAVES)


def wave_targets(tm: Load, index: int, count: int, rack: Rack | None) -> tuple[Load, ...]:
    """Each working set's share of the training max rounded down to the rack; sets past the
    wave's three repeat its heaviest."""
    percents = WAVES[index]
    shares = (
        Load(round(tm.amount * percents[min(i, len(percents) - 1)] / 100, PRECISION), tm.mode)
        for i in range(count)
    )
    if rack is None:
        return tuple(shares)
    return tuple(round_to_rack(rack, share, "cut").load for share in shares)


def rep_out_target(index: int) -> int:
    return int(REP_OUTS[index].rstrip("+"))


def wave_of(exposure: Exposure, tm: Load, rack: Rack | None) -> int | None:
    """Which wave of `tm` an exposure was, read from its top working load."""
    logged = top_on_grid(exposure, rack, tm.mode)
    if logged is None:
        return None
    for index in range(len(WAVES)):
        if wave_targets(tm, index, len(WAVES[index]), rack)[-1] == logged:
            return index
    return None


def rep_out(exposure: Exposure) -> int:
    return exposure.working[-1].reps or 0


def rep_outs_due(history: Sequence[Exposure], tm: Load, rack: Rack | None) -> tuple[int, ...]:
    """The three rep-outs, oldest first, when the newest three ordinary exposures were the third,
    second and first waves at `tm`; empty otherwise."""
    newest = history[: len(WAVES)]
    waves = [wave_of(exposure, tm, rack) for exposure in newest]
    if waves != list(reversed(range(len(WAVES)))):
        return ()
    return tuple(rep_out(exposure) for exposure in reversed(newest))
