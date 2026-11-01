from dataclasses import dataclass
from typing import Literal

from coach.core.config import Units
from coach.core.units import from_kg, to_kg

type LoadMode = Literal[
    "total",
    "per_hand_x2",
    "single_implement",
    "bodyweight",
    "assisted",
    "band",
    "duration",
    "distance",
]


@dataclass(frozen=True)
class Load:
    """`amount` is in athlete units, and per hand under `per_hand_x2`."""

    amount: float
    mode: LoadMode

    @property
    def total(self) -> float:
        return self.amount * 2 if self.mode == "per_hand_x2" else self.amount

    def hevy_kg(self, units: Units) -> float:
        return to_kg(self.total, units)


PRECISION = 2
UNLOADED: frozenset[LoadMode] = frozenset({"bodyweight", "band", "duration", "distance"})


def from_hevy_kg(kg: float | None, mode: LoadMode, units: Units) -> Load | None:
    """A logged Hevy weight as a Load: Hevy holds the total in kg."""
    if kg is None or mode in UNLOADED:
        return None
    total = from_kg(kg, units)
    amount = total / 2 if mode == "per_hand_x2" else total
    return Load(round(amount, PRECISION), mode)
