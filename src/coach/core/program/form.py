"""The authored program form as values (docs/spec/program.md, "The authored form")."""

from collections.abc import Mapping
from dataclasses import dataclass, field
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
class SchemeRef:
    name: str
    params: Mapping[str, object] = field(default_factory=dict[str, object])


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
    weeks: Mapping[str, Mapping[str, str]]

    def slots(self) -> list[tuple[str, str, str]]:
        """Every (rotation week, weekday, session id), in rotation and weekday order."""
        return [
            (week, day, self.weeks[week][day])
            for week in self.rotation
            for day in WEEKDAYS
            if day in self.weeks.get(week, {})
        ]

    def scheduled(self) -> frozenset[str]:
        return frozenset(session for _, _, session in self.slots())


@dataclass(frozen=True)
class Dose:
    per_muscle: int
    lift: Mapping[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True)
class Deload:
    hard_weeks_ceiling: int
    set_cut_pct: Number
    load_cut_pct: Number
    rpe_cap: Number
    test_priority_lifts: bool


@dataclass(frozen=True)
class AcknowledgeEntry:
    flag: str
    because: str
    text: str


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
            "schedule": {
                "rotation": list(self.schedule.rotation),
                **{week: dict(days) for week, days in self.schedule.weeks.items()},
            },
        }
        if self.dose is not None:
            document["dose"] = {"per_muscle": self.dose.per_muscle, "lift": dict(self.dose.lift)}
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
            document["acknowledge"] = [
                {"flag": a.flag, "because": a.because, "text": a.text}
                for a in self.acknowledgements
            ]
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
    document["sets"] = [_group_document(group) for group in line.sets]
    document["rest_s"] = line.rest_s
    optional: dict[str, object | None] = {
        "cues": line.cues,
        "scheme": scheme_document(line.scheme),
        "start_load": line.start_load,
        "superset": line.superset,
    }
    document |= {key: value for key, value in optional.items() if value is not None}
    return document


def _group_document(group: SetGroup) -> dict[str, object]:
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
