import datetime
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from coach.core.draft_fields import Fields, required
from coach.core.errors import Invalid
from coach.core.ref import REF_KINDS, Ref
from coach.core.registries.ledger import CONSTRAINT_KINDS, FOLLOW_UP_EVENTS, NIGGLE_STATUSES
from coach.core.registries.program import LOAD_MODES, SET_TYPES

type Json = Mapping[str, object]

REHAB_CADENCES = ("standing", "daily")
TIERS = ("core", "optional")
OPEN_REPS = re.compile(r"[1-9][0-9]*\+")


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
    """A follow-up event. With `text` and no `followup` it raises one as a `kept` event."""

    kind: str
    date: datetime.date
    due: datetime.date | None = None
    followup: str | None = None
    raised_text: str | None = None
    about: Ref | None = None
    text: str | None = None
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
    opened = f.date("opened") if named is None else None
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
            opened=opened or (date if named is None else None),
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
    named = f.text("followup")
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
            followup=named,
            text=f.text("text"),
            key=f.key(),
        )
    )
