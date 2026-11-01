from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from coach.core.registries.registry import Registry, Row

type CadenceSignal = Literal["cadence_slow", "cadence_fast"]
type ParamType = Literal[
    "integer", "fraction", "percent", "number", "loads", "per_exercise", "number_or_per_exercise"
]
type SetGroupShape = Literal["any", "one_working", "top_then_backoffs", "count_only"]
type RpeOn = Literal["every_working", "top", "none"]


@dataclass(frozen=True)
class Param:
    """`default` is `None` when the form must state the param."""

    name: str
    type: ParamType
    default: int | float | None = None

    @property
    def required(self) -> bool:
        return self.default is None

    def describe(self) -> Row:
        row: Row = {"name": self.name, "type": self.type}
        if self.required:
            row["required"] = True
        else:
            row["default"] = self.default
        return row


LINE_SET_TYPES = ("warm_up", "working", "activation")


@dataclass(frozen=True)
class Scheme:
    name: str
    level: Literal["line", "session"]
    reads: str
    params: tuple[Param, ...] = ()
    set_types: tuple[str, ...] = ()
    set_groups: SetGroupShape = "any"
    rpe_on: RpeOn = "none"
    opening: str | None = None
    holds: Mapping[str, object] = field(default_factory=dict[str, object])
    reads_training_max: bool = False
    cadence_signals: tuple[CadenceSignal, ...] = ()

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def describe(self) -> Row:
        row: Row = {
            "name": self.name,
            "level": self.level,
            "params": [p.describe() for p in self.params],
        }
        if self.level == "line":
            row |= {
                "set_types": list(self.set_types),
                "set_groups": self.set_groups,
                "rpe_on": self.rpe_on,
                "opening": self.opening,
            }
        row["reads"] = self.reads
        if self.holds:
            row["holds"] = dict(self.holds)
        return row | {
            "reads_training_max": self.reads_training_max,
            "cadence_signals": list(self.cadence_signals),
        }


# docs/spec/program.md, "Schemes"; the signals each can raise are goals.md's "Cadence signals".
SCHEMES = Registry(
    "schemes",
    (
        Scheme(
            "double_progression",
            "line",
            reads="reps at the authored RPE on the line's anchor exposures",
            set_types=LINE_SET_TYPES,
            rpe_on="every_working",
            opening="start_load at the bottom of the rep range",
            cadence_signals=("cadence_slow", "cadence_fast"),
        ),
        Scheme(
            "linear",
            "line",
            reads="the anchor's load and whether its sets were made",
            params=(
                Param("misses_before_reset", "integer", 2),
                Param("reset_factor", "fraction", 0.9),
            ),
            set_types=LINE_SET_TYPES,
            rpe_on="every_working",
            opening="start_load, the authored sets",
            cadence_signals=("cadence_slow",),
        ),
        Scheme(
            "hold",
            "line",
            reads="the anchor's top load, nothing else",
            set_types=LINE_SET_TYPES,
            opening="the authored sets, start_load where load-bearing",
        ),
        Scheme(
            "assistance_ladder",
            "line",
            reads="reps at RPE on the current rung",
            params=(Param("rungs", "loads"),),
            set_types=("working",),
            set_groups="one_working",
            rpe_on="every_working",
            opening="the first rung",
            cadence_signals=("cadence_slow",),
        ),
        Scheme(
            "top_backoff",
            "line",
            reads="the exercise-wide e1RM, the top group's RPE as a cap",
            params=(Param("pct_of_top", "percent"),),
            set_types=("warm_up", "working"),
            set_groups="top_then_backoffs",
            rpe_on="top",
            opening="start_load is the top set; back-offs derive from it",
            cadence_signals=("cadence_slow", "cadence_fast"),
        ),
        Scheme(
            "wave_531",
            "line",
            reads=(
                "the current training_max Decision on the exercise, the Block's hard-week count "
                "and the last rep-out"
            ),
            set_types=("warm_up", "working"),
            set_groups="count_only",
            opening="start_load is the training max until a Decision exists",
            holds={
                "waves": [[65, 75, 85], [70, 80, 90], [75, 85, 95]],
                "reps": ["5+", "3+", "1+"],
            },
            reads_training_max=True,
            cadence_signals=("cadence_slow",),
        ),
        Scheme(
            "emom_density",
            "session",
            reads="the last matched Activity",
            params=(
                Param("minutes", "integer"),
                Param("minutes_cap", "integer"),
                Param("minutes_step", "integer"),
                Param("reps", "per_exercise"),
                Param("reps_cap", "number_or_per_exercise"),
                Param("rpe_target", "number"),
            ),
        ),
        Scheme(
            "circuit_rounds",
            "session",
            reads="the last matched Activity",
            params=(
                Param("rounds", "integer"),
                Param("rounds_cap", "integer"),
                Param("time_cap_minutes", "integer"),
                Param("reps", "per_exercise"),
                Param("rpe_target", "number"),
            ),
        ),
    ),
)
