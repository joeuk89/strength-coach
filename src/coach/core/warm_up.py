"""Warm-up targets (docs/spec/prescription.md, "Warm-ups"): the registry ramp over the first
working load, then the ADR 0008 ladder. The ramp is this framework's heuristic, with no `rn:`."""

from collections.abc import Sequence

from coach.core.load import Load
from coach.core.rack import Rack, warm_up_ladder

RAMP_PCT: dict[int, tuple[float, ...]] = {1: (60,), 2: (50, 75), 3: (40, 60, 80)}
SPREAD_PCT = (40, 80)
PRECISION = 4


def ramp(count: int) -> tuple[float, ...]:
    if count in RAMP_PCT:
        return RAMP_PCT[count]
    low, high = SPREAD_PCT
    return tuple(low + i * (high - low) / (count - 1) for i in range(count))


def warm_up_loads(
    first_working: Load, count: int, rack: Rack | None
) -> tuple[tuple[float, ...], tuple[Load, ...]]:
    """The ramp's targets and the loads they ladder to; with no rack the targets stand."""
    targets = tuple(round(first_working.amount * pct / 100, PRECISION) for pct in ramp(count))
    amounts: Sequence[float] = (
        targets if rack is None else [row.load for row in warm_up_ladder(rack, targets)]
    )
    return targets, tuple(Load(amount, first_working.mode) for amount in amounts)
