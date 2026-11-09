"""What `prescribe` is handed and what it returns (docs/spec/prescription.md, "What prescribe is
handed" and "What the agent is handed"). The request is rebuilt on demand and never stored."""

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from coach.core.config import Units
from coach.core.days_off import SessionTrained
from coach.core.exposure import Exposure
from coach.core.flag import Flag
from coach.core.load import Load, LoadMode
from coach.core.program.form import Line, Number, ProgramForm, Reps
from coach.core.rack import Rack

type StepValue = float | str | tuple[float, ...] | None


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
class RungNaming:
    """What a rung's label reads beyond its ladder: the athlete's units for a load and the
    library's exercise names. An exercise missing from `names` shows its id."""

    units: Units
    names: Mapping[str, str]

    def name(self, exercise_id: str) -> str:
        return self.names.get(exercise_id, exercise_id)


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
    """One typed departure on the plan, scoped by the refs it carries (docs/spec/overrides.md,
    "WeekPlan overrides"); `params` holds the kind's params as parsed values."""

    kind: str
    session_id: str | None = None
    exercise_id: str | None = None
    date: datetime.date | None = None
    params: Mapping[str, object] = field(default_factory=dict[str, object])
    because: str | None = None
    text: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionInForce:
    id: str
    kind: str
    session_id: str | None = None
    exercise_id: str | None = None
    params: Mapping[str, object] = field(default_factory=dict[str, object])
    on: datetime.date | None = None


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
    """A conditioning session's last matched workout: its reps per exercise, and its rounds
    under `circuit_rounds`."""

    date: datetime.date
    minutes: int | None
    rpe: float | None
    reps: Mapping[str, int] = field(default_factory=dict[str, int])
    rounds: int | None = None


@dataclass(frozen=True)
class PrescribeRequest:
    """`redesigned` is the latest redesign's adoption date; `None` reads stalls unbounded.
    `adopted` is the version's own adoption date, where a ladder's first rung starts."""

    version: ProgramVersion
    exposures: tuple[Exposure, ...]
    racks: Mapping[str, Mapping[str, Rack]]
    planned: PlannedSession
    rung_naming: RungNaming
    trained: tuple[SessionTrained, ...] = ()
    overrides: tuple[PlanOverride, ...] = ()
    decisions: tuple[DecisionInForce, ...] = ()
    niggle_constraints: tuple[NiggleConstraint, ...] = ()
    status_spans: tuple[StatusSpan, ...] = ()
    hard_week_count: int = 0
    activities: Mapping[str, MatchedActivity] = field(default_factory=dict[str, MatchedActivity])
    redesigned: datetime.date | None = None
    adopted: datetime.date | None = None


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


def rung_step_back(standing: int, week: int, cause: str) -> Step:
    return Step("cut", f"rung {standing}", f"rung {week}", cause)


def stepped_back_a_rung(steps: Iterable[Mapping[str, object]]) -> bool:
    """A frozen line's step back. A WeekPlan frozen when the step named exercises reads False, so
    it keeps projecting the note it pushed and raises no false drift."""
    return any(
        step.get("step") == "cut" and str(step.get("from")).startswith("rung ") for step in steps
    )


@dataclass(frozen=True)
class PrescribedGroup:
    type: str
    count: int
    load: Load | None = None
    reps: Reps | None = None
    duration_s: int | None = None
    rpe: Number | None = None
    rpe_cap: Number | None = None


@dataclass(frozen=True)
class LinePrescription:
    exercise_id: str
    scheme: str
    groups: tuple[PrescribedGroup, ...]
    derived_from: str | None
    steps: tuple[Step, ...]
    flags: tuple[Flag, ...]
    change: str
    rung: int | None = None


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
