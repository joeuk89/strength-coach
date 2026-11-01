import datetime
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, cast

from coach.core.draft_fields import Fields, required
from coach.core.errors import Invalid
from coach.core.flag import FlagKey
from coach.core.overrides import line_override
from coach.core.ref import REF_KINDS, Ref
from coach.core.registries.flags import FLAGS
from coach.core.registries.ledger import (
    CONSTRAINT_KINDS,
    DECISION_KINDS,
    FOLLOW_UP_EVENTS,
    NIGGLE_STATUSES,
    REASONS,
)
from coach.core.registries.log import ANNOTATION_KINDS
from coach.core.registries.program import LOAD_MODES, SET_TYPES

type Json = Mapping[str, object]

REHAB_CADENCES = ("standing", "daily")
TIERS = ("core", "optional")
OPEN_REPS = re.compile(r"[1-9][0-9]*\+")
BLOCK_ID = re.compile(r"b-\d{4}-\d{2}-\d{2}")
DECISION_ID = re.compile(r"d-\d+")
# check-in.md, "The sourced records": what each annotation kind is about.
ON_PLANNED_SESSION = ("trained_unlogged", "cancelled", "miss_tag")
ACTIVITY_CAPS = (("weekly_distance", "weekly_minutes"), ("single_distance", "single_minutes"))


@dataclass(frozen=True)
class Constraint:
    kind: str
    exercise: str | None = None
    pattern: str | None = None
    value: float | None = None


@dataclass(frozen=True)
class RehabSession:
    """A session the niggle carries; each line is a `program_line` row minus its keys."""

    session: str
    title: str
    cadence: str
    lines: tuple[Json, ...]
    tier: str = "optional"
    location: str | None = None


@dataclass(frozen=True)
class NiggleRecord:
    """A niggle status event. With `site` it raises the niggle; with `niggle` it names one."""

    date: datetime.date
    status: str
    constraints: tuple[Constraint, ...] = ()
    niggle: str | None = None
    site: str | None = None
    opened: datetime.date | None = None
    rehab: RehabSession | None = None
    text: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class FollowUpRecord:
    """A follow-up event. With `text` and no `follow_up` it raises one as a `kept` event."""

    kind: str
    date: datetime.date
    due: datetime.date | None = None
    follow_up: str | None = None
    raised_text: str | None = None
    about: Ref | None = None
    text: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class DecisionRecord:
    """A Decision: its kind, the two ids the supersede rule keys on, the kind's other params,
    and the reason triple."""

    kind: str
    because: str
    text: str
    params: Json
    session: str | None = None
    exercise: str | None = None
    until: datetime.date | None = None
    evidence: tuple[Ref, ...] = ()
    key: str | None = None


@dataclass(frozen=True)
class AnnotationRecord:
    """An annotation, or with `withdraws` the withdrawal of one: the writer copies its columns.
    A miss_tag's `because` is the miss tag."""

    kind: str | None = None
    target: Ref | None = None
    because: str | None = None
    params: Json | None = None
    text: str | None = None
    withdraws: str | None = None
    key: str | None = None


def parse_niggle(f: Fields) -> NiggleRecord:
    named = f.text("niggle")
    site = f.text("site", required=named is None)
    if named is not None and site is not None:
        raise Invalid(
            "invalid_argument",
            f"{f.where}: name a stored niggle with niggle, or raise one with site; not both",
        )
    date = required(f.date("date", required=True))
    status = required(f.term("status", NIGGLE_STATUSES, required=True))
    constraints = tuple(_constraint(c) for c in f.tables("constraints"))
    if status == "resolved" and constraints:
        raise Invalid(
            "niggle_constraint_on_resolved",
            f"{f.where}: a resolved event carries no constraints; a resolved niggle binds nothing",
        )
    opened = (f.date("opened") or date) if named is None else None
    rehab = f.subtable("rehab")
    if rehab is not None and named is not None:
        raise Invalid(
            "invalid_argument",
            f"{f.where}: a rehab session is raised with the niggle, on the event that opens it",
        )
    return f.done(
        NiggleRecord(
            date=date,
            status=status,
            constraints=constraints,
            niggle=named,
            site=site,
            opened=opened,
            rehab=_rehab(rehab) if rehab else None,
            text=f.text("text"),
            key=f.key(),
        )
    )


def _constraint(f: Fields) -> Constraint:
    kind = required(f.term("kind", CONSTRAINT_KINDS, required=True))
    exercise = f.text("exercise")
    pattern = f.text("pattern")
    value = f.number("value")
    # prescription.md, "Niggle constraints": the scope table the CHECKs encode.
    if exercise and pattern:
        raise f.wrong("exercise", "given alone; a constraint names an exercise or a pattern")
    if CONSTRAINT_KINDS.get(kind).takes_value != (value is not None):
        wanted = "given" if value is None else "left out"
        raise Invalid("invalid_argument", f"{f.where}: value must be {wanted} on {kind}")
    if kind == "load_cap" and exercise is None:
        raise f.wrong("exercise", "given; a load_cap names one exercise")
    if kind == "avoid" and exercise is None and pattern is None:
        raise f.wrong("exercise", "given, or pattern; avoid names one of them")
    return f.done(Constraint(kind, exercise, pattern, value))


def _rehab(f: Fields) -> RehabSession:
    lines = f.tables("line")
    if not lines:
        raise f.wrong("line", "at least one [[niggle.rehab.line]]")
    return f.done(
        RehabSession(
            session=required(f.text("session", required=True)),
            title=required(f.text("title", required=True)),
            cadence=required(f.choice("cadence", REHAB_CADENCES, required=True)),
            tier=f.choice("tier", TIERS) or "optional",
            location=f.text("location"),
            lines=tuple(_rehab_line(position, line) for position, line in enumerate(lines)),
        )
    )


def _rehab_line(position: int, f: Fields) -> Json:
    groups = f.tables("sets")
    if not groups:
        raise f.wrong("sets", "at least one set group")
    return f.done(
        {
            "exercise_id": required(f.text("exercise", required=True)),
            "position": position,
            "load_mode": f.term("load_mode", LOAD_MODES),
            "set_groups": [_set_group(g) for g in groups],
            "rest_s": required(f.integer("rest_s", required=True)),
            "cues": f.text("cues"),
            "scheme": {"name": "hold"},
            "start_load": f.number("start_load"),
            "superset": f.text("superset"),
        }
    )


def _set_group(f: Fields) -> Json:
    group: dict[str, object] = {
        "count": required(f.integer("count", required=True)),
        "type": f.term("type", SET_TYPES) or "working",
    }
    reps = f.raw("reps")
    duration = f.integer("duration_s")
    if (reps is None) == (duration is None):
        raise f.wrong("reps", "given, or duration_s; exactly one of them")
    if reps is not None:
        group["reps"] = _reps(reps, f)
    else:
        group["duration_s"] = duration
    rpe = f.number("rpe")
    if rpe is not None:
        group["rpe"] = rpe
    return f.done(group)


def _reps(value: object, f: Fields) -> object:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and OPEN_REPS.fullmatch(value):
        return value
    if isinstance(value, list):
        bounds = cast(list[object], value)
        if len(bounds) == 2 and all(type(n) is int for n in bounds):
            return bounds
    raise f.wrong("reps", 'a whole number, a range [6, 8] or an open top "8+"')


def parse_follow_up(f: Fields) -> FollowUpRecord:
    named = f.text("follow_up")
    if named is None:
        return f.done(
            FollowUpRecord(
                kind="kept",
                date=required(f.date("raised", required=True)),
                due=required(f.date("due", required=True)),
                raised_text=required(f.text("text", required=True)),
                about=f.ref("about", REF_KINDS),
                key=f.key(),
            )
        )
    kind = required(f.term("kind", FOLLOW_UP_EVENTS, required=True))
    # schema.md, follow_up_event: kept and deferred carry the due date, the others none.
    due = f.date("due", required=kind in ("kept", "deferred"))
    if due is not None and kind not in ("kept", "deferred"):
        raise f.wrong("due", f"left out of a {kind} event")
    return f.done(
        FollowUpRecord(
            kind=kind,
            date=required(f.date("date", required=True)),
            due=due,
            follow_up=named,
            text=f.text("text"),
            key=f.key(),
        )
    )


def parse_decision(f: Fields) -> DecisionRecord:
    kind = required(f.term("kind", DECISION_KINDS, required=True))
    rule = DECISION_KINDS.get(kind)
    session = f.text("session", required=True) if "session" in rule.params else None
    exercise = f.text("exercise", required=True) if "exercise" in rule.params else None
    params = {
        name: value
        for name in rule.params
        if name not in ("session", "exercise") and (value := _decision_param(f, name)) is not None
    }
    if kind == "activity_cap":
        _check_activity_cap(f, params)
    # decline_ceiling's until is the Sunday of its week, which the writer fills when left out.
    until = (
        f.date("until", required=rule.until == "required" and kind != "decline_ceiling")
        if rule.until != "none"
        else None
    )
    return f.done(
        DecisionRecord(
            kind=kind,
            because=required(f.term("because", REASONS, required=True)),
            text=required(f.text("text", required=True)),
            params=params,
            session=session,
            exercise=exercise,
            until=until,
            evidence=f.refs("evidence"),
            key=f.key(),
        )
    )


def _decision_param(f: Fields, name: str) -> object | None:
    match name:
        case "override":
            return _line_override(f.subtable(name) or _missing(f, name))
        case "flag":
            return _calendar_free_flag(f, required(f.text(name, required=True)))
        case "params_hash" | "activity_kind":
            return f.text(name, required=True)
        case "load":
            return f.number(name, required=True)
        case "block":
            return _matching(f, name, BLOCK_ID, "a Block id, b-2026-10-05")
        case "decision":
            return _matching(f, name, DECISION_ID, "a Decision id, d-0007")
        case "ref":
            return str(f.ref(name, ("rn",)) or _missing(f, name))
        case _:
            return f.number(name)


def _missing(f: Fields, name: str) -> NoReturn:
    raise Invalid("invalid_argument", f"{f.where}: {name} is required")


def _matching(f: Fields, name: str, pattern: re.Pattern[str], wanted: str) -> str:
    value = required(f.text(name, required=True))
    if not pattern.fullmatch(value):
        raise f.wrong(name, wanted)
    return value


def _line_override(f: Fields) -> Json:
    """Checked as the plan's own line override is, and stored as written."""
    line_override(f.table, where=f.where)
    return dict(f.table)


def _calendar_free_flag(f: Fields, text: str) -> str:
    key = FlagKey.parse(text)
    if key.code not in FLAGS or FLAGS.get(key.code).severity != "warning":
        raise f.wrong("flag", "the key of a registered warning")
    if key.scope.kind == "week" or key.scope.dated:
        raise f.wrong("flag", "a calendar-free key: no week scope and no Monday (validation.md)")
    return text


def _check_activity_cap(f: Fields, params: Json) -> None:
    given = [[name for name in pair if name in params] for pair in ACTIVITY_CAPS]
    if any(len(names) > 1 for names in given):
        raise Invalid(
            "invalid_argument",
            f"{f.where}: an activity_cap takes weekly_distance or weekly_minutes, "
            "and single_distance or single_minutes, never both of a pair",
        )
    if not any(given):
        raise Invalid("invalid_argument", f"{f.where}: an activity_cap names at least one cap")


def supersede_subject(
    kind: str, session: object, exercise: object, params: Json
) -> tuple[object, ...] | None:
    """What a Decision supersedes the earlier in-force one on (overrides.md, "Decision kinds");
    None for the kinds that supersede nothing."""
    match kind:
        case "override":
            return (kind, session, exercise, cast(Json, params["override"])["kind"])
        case "park_session" | "resume_session":
            return ("session", session)
        case "training_max" | "safety_ceiling":
            return (kind, exercise)
        case "leave_warning":
            return (kind, params["flag"])
        case "activity_cap":
            return (kind, params["activity_kind"])
        case "decline_ceiling":
            return (kind, params["block"])
        case "defer_deep_review":
            return (kind,)
        case _:
            return None


def parse_annotation(f: Fields) -> AnnotationRecord:
    if f.has("withdraws"):
        f.only("withdraws", "key")
        return f.done(AnnotationRecord(withdraws=f.text("withdraws"), key=f.key()))
    kind = required(f.term("kind", ANNOTATION_KINDS, required=True))
    target = required(f.ref("target", ("workout", "planned_session")) or _missing(f, "target"))
    wanted = "planned_session" if kind in ON_PLANNED_SESSION else "workout"
    if target.kind != wanted:
        raise f.wrong("target", f"a {wanted} ref for a {kind} annotation")
    params = f.raw("params")
    if params is not None and not isinstance(params, dict):
        raise f.wrong("params", "a table")
    values = cast(Json, params) if params else None
    if kind == "match":
        values = _match_params(f, values)
    return f.done(
        AnnotationRecord(
            kind=kind,
            target=target,
            because=f.term("because", REASONS, required=True),
            params=values,
            text=f.text("text"),
            key=f.key(),
        )
    )


def _match_params(f: Fields, params: Json | None) -> Json:
    params = params or {}
    planned = params.get("planned_session")
    if not isinstance(planned, str) or Ref.parse(planned).kind != "planned_session":
        raise f.wrong("params", "a table naming the planned_session the workout matches")
    return params


def annotation_refs(record: AnnotationRecord) -> tuple[Ref, ...]:
    """The refs an annotation cites: its target, and a match's planned session."""
    if record.target is None:
        return ()
    planned = (record.params or {}).get("planned_session") if record.kind == "match" else None
    return (record.target, *([Ref.parse(planned)] if isinstance(planned, str) else []))
