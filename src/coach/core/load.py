from dataclasses import dataclass
from typing import Literal

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
