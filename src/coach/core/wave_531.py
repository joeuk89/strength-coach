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
from coach.core.program.form import Line, Reps
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
    decisions: Iterable[DecisionInForce], line: Line, mode: LoadMode
) -> TrainingMax | None:
    """The `training_max` Decision in force on the exercise, else the line's start load."""
    for decision in reversed(tuple(decisions)):
        load = decision.params.get("load")
        if (
            decision.kind == "training_max"
            and decision.exercise_id == line.exercise
            and isinstance(load, int | float)
        ):
            return TrainingMax(Load(float(load), mode), decision.id)
    if line.start_load is None:
        return None
    return TrainingMax(Load(line.start_load, mode), "start_load")


def wave_index(hard_week_count: int) -> int:
    return hard_week_count % len(WAVES)


@dataclass(frozen=True)
class WaveSet:
    load: Load
    reps: Reps


def wave_sets(tm: Load, index: int, count: int, rack: Rack | None) -> tuple[WaveSet, ...]:
    percents = WAVES[index]
    base = rep_out_target(index)
    sets: list[WaveSet] = []
    for position in range(count):
        pct = percents[min(position, len(percents) - 1)]
        target = Load(round(tm.amount * pct / 100, PRECISION), tm.mode)
        load = target if rack is None else round_to_rack(rack, target, "cut").load
        last = position == count - 1
        sets.append(WaveSet(load, REP_OUTS[index] if last else base))
    return tuple(sets)


def rep_out_target(index: int) -> int:
    return int(REP_OUTS[index].rstrip("+"))


def wave_of(exposure: Exposure, tm: Load, count: int, rack: Rack | None) -> int | None:
    """Which wave of `tm` an exposure was, read from its last working load."""
    logged = top_on_grid(exposure, rack, tm.mode)
    if logged is None:
        return None
    for index in range(len(WAVES)):
        if wave_sets(tm, index, count, rack)[-1].load == logged:
            return index
    return None


def rep_out(exposure: Exposure) -> int:
    return exposure.working[-1].reps or 0


def rep_outs_due(
    history: Sequence[Exposure], tm: Load, count: int, rack: Rack | None
) -> tuple[int, ...] | None:
    """The three rep-outs, oldest first, when the newest three ordinary exposures were the third,
    second and first waves at `tm`."""
    newest = history[: len(WAVES)]
    waves = [wave_of(exposure, tm, count, rack) for exposure in newest]
    if waves != list(reversed(range(len(WAVES)))):
        return None
    return tuple(rep_out(exposure) for exposure in reversed(newest))
