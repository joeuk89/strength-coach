from dataclasses import dataclass
from typing import Literal

from coach.core.registries.registry import Registry, Row, terms


@dataclass(frozen=True)
class OverrideKind:
    name: str
    scope: Literal["week", "session", "line"]
    params: tuple[str, ...]

    def describe(self) -> Row:
        return {"name": self.name, "scope": self.scope, "params": list(self.params)}


PLAN_STATUSES = terms("plan-statuses", "approved", "superseded")

# docs/spec/overrides.md, "WeekPlan overrides".
OVERRIDE_KINDS = Registry(
    "override-kinds",
    (
        OverrideKind("light_week", "week", ("set_cut_pct", "load_cut_pct", "rpe_cap")),
        OverrideKind("minimum_week", "week", ("keep",)),
        OverrideKind("one_off_week", "week", ("location",)),
        OverrideKind("move_session", "session", ("to",)),
        OverrideKind("drop_session", "session", ()),
        OverrideKind("add_session", "session", ("session", "date", "location")),
        OverrideKind("relocate_session", "session", ("location",)),
        OverrideKind("swap_exercise", "line", ("to", "start_load", "load_mode")),
        OverrideKind("pin_load", "line", ("load",)),
        OverrideKind("hold", "line", ()),
        OverrideKind("restate_sets", "line", ("sets",)),
        OverrideKind("drop_line", "line", ()),
    ),
)
