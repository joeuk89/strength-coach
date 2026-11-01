"""The plan Draft as a value: the week's prescriptions, its rotation position and the Athlete
notes since the last approved WeekPlan (docs/spec/verbs.md, "Drafts written by the engine")."""

import datetime
from dataclasses import dataclass

from coach.core.flag import Flag, Scope, raise_flag
from coach.core.planned_week import RotationPosition
from coach.core.prescription import PlanOverride, SessionPrescription


@dataclass(frozen=True)
class AthleteNote:
    date: datetime.date
    text: str
    about: str | None = None


@dataclass(frozen=True)
class PlanDraft:
    week: datetime.date
    position: RotationPosition
    sessions: tuple[SessionPrescription, ...]
    notes: tuple[AthleteNote, ...] = ()
    supersedes: str | None = None
    overrides: tuple[PlanOverride, ...] = ()
    conflicts: tuple[Flag, ...] = ()
    confirmed: bool = False
    second_week: tuple[Flag, ...] = ()

    @property
    def week_flags(self) -> tuple[Flag, ...]:
        """The engine proposes the position; the Draft confirms it."""
        if self.confirmed:
            return ()
        return (
            raise_flag(
                "rotation_unconfirmed",
                Scope("week", self.week),
                {"inferred_position": self.position.week, "source": self.position.source},
                f"rotation week {self.position.week} is inferred ({self.position.source}); "
                "confirm it in the Draft",
            ),
        )

    @property
    def flags(self) -> tuple[Flag, ...]:
        line_flags = (f for s in self.sessions for line in s.lines for f in line.flags)
        return (*self.week_flags, *self.conflicts, *line_flags, *self.second_week)

    @property
    def line_count(self) -> int:
        return sum(len(session.lines) for session in self.sessions)
