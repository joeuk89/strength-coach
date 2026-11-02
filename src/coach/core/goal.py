import datetime
import tomllib
from dataclasses import dataclass

from coach.core.draft_fields import Fields, draft_hash, required
from coach.core.errors import Invalid
from coach.core.registries.ledger import GOAL_KINDS, MILESTONE_TARGET_KINDS, PHASE_UNTIL_KINDS
from coach.core.registries.phase import PHASE


@dataclass(frozen=True)
class Target:
    """`value` for `e1rm` and `bodyweight_multiple`, `load` and `reps` for `load_x_reps`."""

    kind: str
    value: float | None = None
    load: float | None = None
    reps: int | None = None

    def describe(self) -> dict[str, object]:
        if self.kind == "load_x_reps":
            return {"kind": self.kind, "load": self.load, "reps": self.reps}
        return {"kind": self.kind, "value": self.value}


@dataclass(frozen=True)
class Milestone:
    exercise: str
    target: Target

    def describe(self) -> dict[str, object]:
        return {"exercise": self.exercise, "target": self.target.describe()}


@dataclass(frozen=True)
class Goal:
    kind: str
    because: str
    priority_lifts: tuple[str, ...]
    why: str
    milestones: tuple[Milestone, ...] = ()


@dataclass(frozen=True)
class Until:
    """`value` is a date for `date`, a bodyweight for the bodyweight kinds, absent otherwise."""

    kind: str
    value: datetime.date | float | None = None


@dataclass(frozen=True)
class PhaseOpen:
    kind: str
    rate_pct_bw_per_week: float
    until: Until
    because: str


@dataclass(frozen=True)
class PhaseClose:
    because: str


@dataclass(frozen=True)
class GoalDraft:
    hash: str
    file: str
    goal: Goal
    open: PhaseOpen | None = None
    close: PhaseClose | None = None

    def exercises(self) -> tuple[str, ...]:
        return (*self.goal.priority_lifts, *(m.exercise for m in self.goal.milestones))


def goal_diff(previous: Goal | None, new: Goal) -> dict[str, object] | None:
    """`why` shows only as changed: both texts in full could pass the envelope's budget."""
    if previous is None:
        return None
    diff: dict[str, object] = {}
    if previous.kind != new.kind:
        diff["kind"] = {"from": previous.kind, "to": new.kind}
    if previous.priority_lifts != new.priority_lifts:
        diff["priority_lifts"] = {
            "from": list(previous.priority_lifts),
            "to": list(new.priority_lifts),
        }
    added = [m.describe() for m in new.milestones if m not in previous.milestones]
    removed = [m.describe() for m in previous.milestones if m not in new.milestones]
    if added or removed:
        diff["milestones"] = {"added": added, "removed": removed}
    if previous.why != new.why:
        diff["why"] = True
    return diff


def parse_goal_draft(data: bytes, *, file: str) -> GoalDraft:
    """A `goal adopt` Draft as values (goals.md, "Writing a Goal")."""
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Invalid("invalid_argument", f"{file} is not valid TOML: {error}") from error
    f = Fields(document, file)
    goal = Goal(
        kind=required(f.term("kind", GOAL_KINDS, required=True)),
        because=required(f.text("because", required=True)),
        priority_lifts=_priority_lifts(f),
        why=required(f.text("why", required=True)),
        milestones=tuple(_milestone(m) for m in f.tables("milestones")),
    )
    open_, close = _phase(f.subtable("phase"))
    return f.done(GoalDraft(draft_hash(data), file, goal, open_, close))


def _priority_lifts(f: Fields) -> tuple[str, ...]:
    lifts = f.texts("priority_lifts")
    for lift in lifts:
        if lifts.count(lift) > 1:
            raise Invalid(
                "priority_lift_duplicate",
                f"{f.where}: priority_lifts names {lift!r} twice; name each lift once",
            )
    return lifts


def _milestone(f: Fields) -> Milestone:
    exercise = required(f.text("exercise", required=True))
    target = f.subtable("target")
    if target is None:
        raise Invalid(
            "milestone_target_missing",
            f"{f.where}: the milestone on {exercise!r} has no target; give "
            "target = { kind = ..., ... }",
        )
    return f.done(Milestone(exercise, _target(target)))


def _target(f: Fields) -> Target:
    kind = required(f.term("kind", MILESTONE_TARGET_KINDS, required=True))
    if kind == "load_x_reps":
        load = required(f.number("load", required=True))
        reps = required(f.integer("reps", required=True))
        if reps < 1:
            raise f.wrong("reps", "a whole number of at least 1")
        return f.done(Target(kind, load=load, reps=reps))
    value = required(f.number("value", required=True))
    if value <= 0:
        raise f.wrong("value", "above 0")
    return f.done(Target(kind, value=value))


def _phase(f: Fields | None) -> tuple[PhaseOpen | None, PhaseClose | None]:
    if f is None:
        return None, None
    open_ = f.subtable("open")
    close = f.subtable("close")
    if open_ is None and close is None:
        raise Invalid("invalid_argument", f"{f.where}: [phase] carries open, close or both")
    return f.done(
        (
            parse_phase_open(open_) if open_ else None,
            _phase_close(close) if close else None,
        )
    )


def parse_phase_open(f: Fields) -> PhaseOpen:
    kind = required(f.term("kind", PHASE, required=True))
    rate = f.number("rate_pct_bw_per_week", low=float("-inf"))
    until = f.subtable("until")
    if until is None:
        raise Invalid("invalid_argument", f"{f.where}: until is required")
    return f.done(
        PhaseOpen(
            kind=kind,
            rate_pct_bw_per_week=(
                PHASE.get(kind).default_rate_pct_bw_per_week if rate is None else rate
            ),
            until=_until(until),
            because=required(f.text("because", required=True)),
        )
    )


def _until(f: Fields) -> Until:
    kind = required(f.term("kind", PHASE_UNTIL_KINDS, required=True))
    if kind == "coachs_call":
        if f.has("value"):
            raise f.wrong("value", "absent for coachs_call")
        return f.done(Until(kind))
    if kind == "date":
        return f.done(Until(kind, required(f.date("value", required=True))))
    return f.done(Until(kind, required(f.number("value", required=True))))


def _phase_close(f: Fields) -> PhaseClose:
    return f.done(PhaseClose(required(f.text("because", required=True))))
