"""The authored program form as values (docs/spec/program.md, "The authored form")."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

type Emphasis = Literal["hypertrophy", "strength", "maintenance"]
type Reps = int | tuple[int, int] | str
type Number = int | float

EMPHASES: tuple[Emphasis, ...] = ("hypertrophy", "strength", "maintenance")
TIERS = ("core", "optional")
CADENCES = ("weekly", "standing", "daily")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# The load modes whose start load is a row of the session location's rack (instance.md).
RACK_MODES = ("total", "per_hand_x2", "single_implement")
LOAD_BEARING_MODES = (*RACK_MODES, "assisted", "band")


@dataclass(frozen=True)
class SetGroup:
    count: int
    type: str = "working"
    reps: Reps | None = None
    duration_s: int | None = None
    rpe: Number | None = None

    @property
    def working(self) -> bool:
        return self.type == "working"


@dataclass(frozen=True)
class Advance:
    """An advance criterion as authored; a key left `None` is unsaid."""

    reps: int | None = None
    duration_s: int | None = None
    rpe_at_most: Number | None = None
    exposures: int | None = None
    manual: bool | None = None

    def stated(self) -> dict[str, object]:
        return {key: value for key, value in vars(self).items() if value is not None}


@dataclass(frozen=True)
class Rung:
    exercise: str
    sets: tuple[SetGroup, ...]
    cues: str | None = None
    advance: Advance = Advance()


@dataclass(frozen=True)
class ExerciseLadder:
    rungs: tuple[Rung, ...]
    advance: Advance = Advance()

    def criterion(self, index: int) -> Advance:
        """Rung `index` (from 1)'s criterion: its own keys laid over the ladder's, or `manual`
        alone when the rung says so."""
        own = self.rungs[index - 1].advance
        if own.manual:
            return Advance(manual=True)
        return replace(self.advance, **own.stated())


@dataclass(frozen=True)
class SchemeRef:
    """`params` are as authored; `ladder` is an `exercise_ladder` line's rungs read from them."""

    name: str
    params: Mapping[str, object] = field(default_factory=dict[str, object])
    ladder: ExerciseLadder | None = None


@dataclass(frozen=True)
class Line:
    exercise: str
    sets: tuple[SetGroup, ...]
    rest_s: int
    scheme: SchemeRef
    load_mode: str | None = None
    cues: str | None = None
    start_load: Number | None = None
    superset: str | None = None

    @property
    def ladder(self) -> ExerciseLadder | None:
        return self.scheme.ladder

    @property
    def rung_exercises(self) -> tuple[str, ...]:
        """Each rung's exercise in rung order, none without a ladder."""
        return () if self.ladder is None else tuple(rung.exercise for rung in self.ladder.rungs)

    def working_groups(self) -> tuple[SetGroup, ...]:
        return tuple(group for group in self.sets if group.working)


@dataclass(frozen=True)
class Session:
    id: str
    title: str
    kind: str
    tier: str
    cadence: str | None = None
    location: str | None = None
    minutes: int | None = None
    scheme: SchemeRef | None = None
    estimated_sets: Mapping[str, int] | None = None
    lines: tuple[Line, ...] = ()


@dataclass(frozen=True)
class Schedule:
    rotation: tuple[str, ...]
    weeks: Mapping[str, Mapping[str, tuple[str, ...]]]

    def slots(self) -> list[tuple[str, str, str]]:
        """Every (rotation week, weekday, session id), in rotation, weekday and list order."""
        return [
            (week, day, session_id)
            for week in self.rotation
            for day in WEEKDAYS
            for session_id in self.weeks.get(week, {}).get(day, ())
        ]

    def to_document(self) -> dict[str, object]:
        """A weekday with one session is a bare id, so a one-element list reads as unchanged."""
        return {
            "rotation": list(self.rotation),
            **{
                week: {day: ids[0] if len(ids) == 1 else list(ids) for day, ids in days.items()}
                for week, days in self.weeks.items()
            },
        }

    def scheduled(self) -> frozenset[str]:
        return frozenset(session for _, _, session in self.slots())


@dataclass(frozen=True)
class LiftDose:
    """A priority lift's weekly target and the counted variants whose hard sets add to it."""

    sets: int
    counts: tuple[str, ...] = ()

    def to_document(self) -> object:
        return {"sets": self.sets, "counts": list(self.counts)} if self.counts else self.sets


@dataclass(frozen=True)
class Dose:
    per_muscle: int
    lift: Mapping[str, LiftDose] = field(default_factory=dict[str, LiftDose])

    def counted(self) -> dict[str, tuple[str, ...]]:
        return {lift: dose.counts for lift, dose in self.lift.items()}


@dataclass(frozen=True)
class Deload:
    hard_weeks_ceiling: int
    set_cut_pct: Number
    load_cut_pct: Number
    rpe_cap: Number
    test_priority_lifts: bool


@dataclass(frozen=True)
class AcknowledgeEntry:
    """`params_hash`, when stated, binds the entry to the warning's params as they were."""

    flag: str
    because: str
    text: str
    params_hash: str | None = None

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {"flag": self.flag}
        if self.params_hash is not None:
            document["params_hash"] = self.params_hash
        return document | {"because": self.because, "text": self.text}


@dataclass(frozen=True)
class ProgramForm:
    name: str
    kind: str
    because: str
    emphasis: Emphasis
    location: str
    schedule: Schedule
    sessions: tuple[Session, ...]
    dose: Dose | None = None
    deload: Deload | None = None
    exercises: Mapping[str, Mapping[str, object]] = field(
        default_factory=dict[str, Mapping[str, object]]
    )
    acknowledgements: tuple[AcknowledgeEntry, ...] = ()

    def session(self, id_: str) -> Session | None:
        return next((s for s in self.sessions if s.id == id_), None)

    def first_line(self, exercise_id: str) -> Line | None:
        return next(
            (line for s in self.sessions for line in s.lines if line.exercise == exercise_id), None
        )

    def locations(self) -> tuple[str, ...]:
        named = [self.location, *(s.location for s in self.sessions if s.location)]
        return tuple(dict.fromkeys(named))

    def to_document(self) -> dict[str, object]:
        """The form as the TOML document it is authored as; the stored `form` is the same."""
        document: dict[str, object] = {
            "name": self.name,
            "kind": self.kind,
            "because": self.because,
            "emphasis": self.emphasis,
            "location": self.location,
            "schedule": self.schedule.to_document(),
        }
        if self.dose is not None:
            document["dose"] = {
                "per_muscle": self.dose.per_muscle,
                "lift": {lift: dose.to_document() for lift, dose in self.dose.lift.items()},
            }
        if self.deload is not None:
            document["deload"] = {
                "hard_weeks_ceiling": self.deload.hard_weeks_ceiling,
                "set_cut_pct": self.deload.set_cut_pct,
                "load_cut_pct": self.deload.load_cut_pct,
                "rpe_cap": self.deload.rpe_cap,
                "test_priority_lifts": self.deload.test_priority_lifts,
            }
        document["session"] = [session_document(s) for s in self.sessions]
        if self.exercises:
            document["exercise"] = {id_: dict(fields) for id_, fields in self.exercises.items()}
        if self.acknowledgements:
            document["acknowledge"] = [a.to_document() for a in self.acknowledgements]
        return document


def session_document(session: Session) -> dict[str, object]:
    document: dict[str, object] = {
        "id": session.id,
        "title": session.title,
        "kind": session.kind,
        "tier": session.tier,
    }
    optional: dict[str, object | None] = {
        "cadence": session.cadence,
        "location": session.location,
        "minutes": session.minutes,
        "scheme": scheme_document(session.scheme) if session.scheme else None,
        "estimated_sets": dict(session.estimated_sets) if session.estimated_sets else None,
    }
    document |= {key: value for key, value in optional.items() if value is not None}
    if session.lines:
        document["line"] = [line_document(line) for line in session.lines]
    return document


def line_document(line: Line) -> dict[str, object]:
    document: dict[str, object] = {"exercise": line.exercise}
    if line.load_mode is not None:
        document["load_mode"] = line.load_mode
    if line.ladder is None:
        document["sets"] = [group_document(group) for group in line.sets]
    document["rest_s"] = line.rest_s
    optional: dict[str, object | None] = {
        "cues": line.cues,
        "scheme": scheme_document(line.scheme),
        "start_load": line.start_load,
        "superset": line.superset,
    }
    document |= {key: value for key, value in optional.items() if value is not None}
    return document


def group_document(group: SetGroup) -> dict[str, object]:
    document: dict[str, object] = {"count": group.count}
    if group.type != "working":
        document["type"] = group.type
    reps = list(group.reps) if isinstance(group.reps, tuple) else group.reps
    optional: dict[str, object | None] = {
        "reps": reps,
        "duration_s": group.duration_s,
        "rpe": group.rpe,
    }
    return document | {key: value for key, value in optional.items() if value is not None}


def scheme_document(scheme: SchemeRef) -> dict[str, object]:
    return {"name": scheme.name, **scheme.params}
