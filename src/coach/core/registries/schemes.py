from dataclasses import dataclass
from typing import Literal

from coach.core.registries.registry import Registry, Row

type CadenceSignal = Literal["cadence_slow", "cadence_fast"]


@dataclass(frozen=True)
class Scheme:
    name: str
    level: Literal["line", "session"]
    reads_training_max: bool = False
    cadence_signals: tuple[CadenceSignal, ...] = ()

    def describe(self) -> Row:
        return {
            "name": self.name,
            "level": self.level,
            "reads_training_max": self.reads_training_max,
            "cadence_signals": list(self.cadence_signals),
        }


# docs/spec/program.md, "Schemes"; the signals each can raise are goals.md's "Cadence signals".
SCHEMES = Registry(
    "schemes",
    (
        Scheme("double_progression", "line", cadence_signals=("cadence_slow", "cadence_fast")),
        Scheme("linear", "line", cadence_signals=("cadence_slow",)),
        Scheme("hold", "line"),
        Scheme("assistance_ladder", "line", cadence_signals=("cadence_slow",)),
        Scheme("top_backoff", "line", cadence_signals=("cadence_slow", "cadence_fast")),
        Scheme("wave_531", "line", reads_training_max=True, cadence_signals=("cadence_slow",)),
        Scheme("emom_density", "session"),
        Scheme("circuit_rounds", "session"),
    ),
)
