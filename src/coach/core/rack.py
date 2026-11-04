"""Racks: the loads one implement can be set to at a location (ADR 0008, docs/spec/instance.md)."""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from coach.core.config import GridImplement, IncrementImplement
from coach.core.load import Load

PRECISION = 6


@dataclass(frozen=True)
class Position:
    name: str
    plates: tuple[float, ...]


@dataclass(frozen=True)
class RackRow:
    """`positions` is `None` where the plates are unknown: every grid location. `hardware` is the
    hardware id of the kit table the row came from, `None` where that table carries none."""

    load: float
    positions: tuple[Position, ...] | None = None
    hardware: str | None = None

    @property
    def plates_per_side(self) -> int:
        return max((len(position.plates) for position in self.positions or ()), default=0)

    def keeps_plates_of(self, earlier: "RackRow") -> bool:
        """Every plate on each of `earlier`'s positions is still on this row's same position."""
        mine = {position.name: Counter(position.plates) for position in self.positions or ()}
        return all(
            Counter(position.plates) <= mine.get(position.name, Counter())
            for position in earlier.positions or ()
        )


class Rack(Protocol):
    @property
    def bottom(self) -> RackRow: ...

    @property
    def top(self) -> RackRow | None:
        """`None` when the rack is unbounded above."""
        ...

    def row_above(self, load: float) -> RackRow | None: ...

    def row_below(self, load: float) -> RackRow | None: ...

    def rows_within(self, low: float, high: float) -> tuple[RackRow, ...]: ...


@dataclass(frozen=True)
class ListedRack:
    rows: tuple[RackRow, ...]

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("a rack has at least one row")
        object.__setattr__(self, "rows", tuple(sorted(self.rows, key=lambda row: row.load)))

    @property
    def bottom(self) -> RackRow:
        return self.rows[0]

    @property
    def top(self) -> RackRow | None:
        return self.rows[-1]

    def row_above(self, load: float) -> RackRow | None:
        return next((row for row in self.rows if _above(row.load, load)), None)

    def row_below(self, load: float) -> RackRow | None:
        return next((row for row in reversed(self.rows) if _above(load, row.load)), None)

    def rows_within(self, low: float, high: float) -> tuple[RackRow, ...]:
        return tuple(
            row for row in self.rows if not _above(low, row.load) and not _above(row.load, high)
        )


@dataclass(frozen=True)
class IncrementRack:
    increment: float
    base: float = 0
    max: float | None = None

    @property
    def bottom(self) -> RackRow:
        return RackRow(self.base)

    @property
    def top(self) -> RackRow | None:
        top_step = self._top_step()
        return None if top_step is None else self._row(top_step)

    def row_above(self, load: float) -> RackRow | None:
        step = max(math.floor(self._steps(load)) + 1, 0)
        top_step = self._top_step()
        return None if top_step is not None and step > top_step else self._row(step)

    def row_below(self, load: float) -> RackRow | None:
        step = self._capped(math.ceil(self._steps(load)) - 1)
        return None if step < 0 else self._row(step)

    def rows_within(self, low: float, high: float) -> tuple[RackRow, ...]:
        first = max(math.ceil(self._steps(low)), 0)
        last = self._capped(math.floor(self._steps(high)))
        return tuple(self._row(step) for step in range(first, last + 1))

    def _steps(self, load: float) -> float:
        return round((load - self.base) / self.increment, PRECISION)

    def _row(self, step: int) -> RackRow:
        return RackRow(round(self.base + step * self.increment, PRECISION))

    def _top_step(self) -> int | None:
        return None if self.max is None else math.floor(self._steps(self.max))

    def _capped(self, step: int) -> int:
        top_step = self._top_step()
        return step if top_step is None else min(step, top_step)


def grid_rack(implement: GridImplement) -> Rack:
    if isinstance(implement, IncrementImplement):
        return IncrementRack(implement.increment, implement.base, implement.max)
    return ListedRack(tuple(RackRow(load) for load in implement.rack))


def on_rack(rack: Rack, amount: float) -> bool:
    return bool(rack.rows_within(amount, amount))


def rows_beside(rack: Rack, amount: float) -> tuple[float, ...]:
    return tuple(row.load for row in (rack.row_below(amount), rack.row_above(amount)) if row)


def _above(load: float, other: float) -> bool:
    return round(load - other, PRECISION) > 0


type Rounding = Literal["step_up", "cut", "hold"]
type RoundingCause = Literal["row", "rack_top"]


@dataclass(frozen=True)
class Rounded:
    load: Load
    cause: RoundingCause


def round_to_rack(rack: Rack, load: Load, rounding: Rounding) -> Rounded:
    """A step-up goes to the nearest row, a cut or hold to the nearest no heavier (ADR 0008)."""
    top = rack.top
    if top is not None and _above(load.amount, top.load):
        return Rounded(_at(load, top), "rack_top")
    on_or_below = _row_on_or_below(rack, load.amount)
    above = rack.row_above(load.amount)
    if rounding == "step_up":
        row = _nearest(load.amount, on_or_below, above)
    elif load.mode == "assisted":
        # Under assistance a heavier load is easier, so "no heavier" means no less assistance.
        row = _row_on_or_above(rack, load.amount)
    else:
        row = on_or_below or rack.bottom
    return Rounded(_at(load, row), "row")


def next_row_up(rack: Rack, load: Load) -> Rounded:
    row = rack.row_above(load.amount)
    return Rounded(load, "rack_top") if row is None else Rounded(_at(load, row), "row")


def next_row_down(rack: Rack, load: Load) -> Load | None:
    row = rack.row_below(load.amount)
    return None if row is None else _at(load, row)


def _row_on_or_below(rack: Rack, amount: float) -> RackRow | None:
    exact = rack.rows_within(amount, amount)
    return exact[0] if exact else rack.row_below(amount)


def _row_on_or_above(rack: Rack, amount: float) -> RackRow:
    exact = rack.rows_within(amount, amount)
    row = exact[0] if exact else rack.row_above(amount)
    assert row is not None, "a load at or under the top row has a row on or above it"
    return row


def _nearest(amount: float, below: RackRow | None, above: RackRow | None) -> RackRow:
    if below is None or above is None:
        row = below or above
        assert row is not None, "a rack has at least one row"
        return row
    return above if _above(amount - below.load, above.load - amount) else below


def _at(load: Load, row: RackRow) -> Load:
    return replace(load, amount=row.load)


WARM_UP_BAND = 0.9


def warm_up_ladder(rack: Rack, targets: Sequence[float]) -> tuple[RackRow, ...]:
    """Each target's row: fewest plates per side from 10 % under it up to it (ADR 0008)."""
    ladder: list[RackRow] = []
    for target in targets:
        previous = ladder[-1] if ladder else None
        ladder.append(_warm_up_row(rack, target, previous))
    return tuple(ladder)


def _warm_up_row(rack: Rack, target: float, previous: RackRow | None) -> RackRow:
    band = rack.rows_within(target * WARM_UP_BAND, target)
    if not band:
        return _row_on_or_below(rack, target) or rack.bottom
    if any(row.positions is None for row in band):
        return band[-1]
    return min(
        band,
        key=lambda row: (
            row.plates_per_side,
            previous is not None and not row.keeps_plates_of(previous),
            row.load,
        ),
    )
