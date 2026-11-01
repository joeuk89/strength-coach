"""What `prescribe` is handed and what it returns (docs/spec/prescription.md, "What prescribe is
handed" and "What the agent is handed"). The request is rebuilt on demand and never stored."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field

from coach.core.days_off import SessionTrained
from coach.core.exposure import Exposure
from coach.core.flag import Flag
from coach.core.load import Load, LoadMode
from coach.core.program.form import Line, Number, ProgramForm, Reps
from coach.core.rack import Rack

type StepValue = float | tuple[float, ...] | None


@dataclass(frozen=True)
class ExerciseFacts:
    load_mode: LoadMode
    equipment_kind: str
    pattern: str | None = None


@dataclass(frozen=True)
class ProgramVersion:
    """The filled form and the library rows of the exercises its lines name."""

    form: ProgramForm
    exercises: Mapping[str, ExerciseFacts]


@dataclass(frozen=True)
class PlannedSession:
    session_id: str
    date: datetime.date
    location: str
    kind: str
    lines: tuple[Line, ...]
    cadence: str = "weekly"
    tier: str = "core"


@dataclass(frozen=True)
class PlanOverride:
    kind: str
    session_id: str | None = None
    exercise_id: str | None = None
    date: datetime.date | None = None
    params: Mapping[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class DecisionInForce:
    id: str
    kind: str
    session_id: str | None = None
    exercise_id: str | None = None
    params: Mapping[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class NiggleConstraint:
    niggle_id: str
    kind: str
    exercise_id: str | None = None
    pattern: str | None = None
    value: float | None = None


@dataclass(frozen=True)
class StatusSpan:
    kind: str
    from_date: datetime.date
    to_date: datetime.date | None = None

    def covers(self, day: datetime.date) -> bool:
        return self.from_date <= day and (self.to_date is None or day <= self.to_date)


@dataclass(frozen=True)
class MatchedActivity:
    """A conditioning session's last matched workout."""

    date: datetime.date
    minutes: int | None
    rpe: float | None
    reps: Mapping[str, int] = field(default_factory=dict[str, int])
    rounds: int | None = None


@dataclass(frozen=True)
class PrescribeRequest:
    version: ProgramVersion
    exposures: tuple[Exposure, ...]
    racks: Mapping[str, Mapping[str, Rack]]
    planned: PlannedSession
    trained: tuple[SessionTrained, ...] = ()
    overrides: tuple[PlanOverride, ...] = ()
    decisions: tuple[DecisionInForce, ...] = ()
    niggle_constraints: tuple[NiggleConstraint, ...] = ()
    status_spans: tuple[StatusSpan, ...] = ()
    hard_week_count: int = 0
    activities: Mapping[str, MatchedActivity] = field(default_factory=dict[str, MatchedActivity])


@dataclass(frozen=True)
class Step:
    """One derivation step: `(step, from, to, cause)`."""

    step: str
    from_: StepValue
    to: StepValue
    cause: str

    def to_json(self) -> dict[str, object]:
        def value(v: StepValue) -> object:
            return list(v) if isinstance(v, tuple) else v

        return {
            "step": self.step,
            "from": value(self.from_),
            "to": value(self.to),
            "cause": self.cause,
        }


@dataclass(frozen=True)
class PrescribedGroup:
    type: str
    count: int
    load: Load | None = None
    reps: Reps | None = None
    duration_s: int | None = None
    rpe: Number | None = None


@dataclass(frozen=True)
class LinePrescription:
    exercise_id: str
    scheme: str
    groups: tuple[PrescribedGroup, ...]
    derived_from: str | None
    steps: tuple[Step, ...]
    flags: tuple[Flag, ...]
    change: str


@dataclass(frozen=True)
class ConditioningDose:
    """A conditioning session's dose from its session scheme; `minutes` is the time cap under
    `circuit_rounds`."""

    scheme: str
    minutes: int | None
    rounds: int | None
    reps: Mapping[str, int]
    derived_from: str
    change: str


@dataclass(frozen=True)
class SessionPrescription:
    session: PlannedSession
    lines: tuple[LinePrescription, ...]
    dose: ConditioningDose | None = None
