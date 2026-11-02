"""A closed week as one value: its kind, its planned sessions as they counted and the dose it
delivered (docs/spec/week.md)."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from coach.core.closed_week.kind import ORDINARY, WeekKind
from coach.core.closed_week.sessions import SessionOutcome


@dataclass(frozen=True)
class ClosedWeek:
    monday: datetime.date
    kind: WeekKind
    sessions: tuple[SessionOutcome, ...] = ()
    dose: Mapping[str, float] = field(default_factory=dict[str, float])
    dose_target: int | None = None
    lift_dose: Mapping[str, int] = field(default_factory=dict[str, int])
    lift_dose_target: Mapping[str, int] = field(default_factory=dict[str, int])

    @property
    def ordinary(self) -> bool:
        return self.kind in ORDINARY

    @property
    def adherence_planned(self) -> int:
        return sum(1 for s in self.sessions if s.in_adherence)

    @property
    def adherence_trained(self) -> int:
        return sum(1 for s in self.sessions if s.in_adherence and s.trained)
