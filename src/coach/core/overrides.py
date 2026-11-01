"""The plan's typed overrides read from the Draft, and the pairs the precedence table forbids
(docs/spec/overrides.md, "WeekPlan overrides", "Draft shape", "Precedence and conflicts")."""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
from typing import cast

from coach.core.draft_fields import Fields, required
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.prescription import PlanOverride
from coach.core.program.form import SetGroup
from coach.core.program.parse import parse_set_groups
from coach.core.registries.ledger import REASONS
from coach.core.registries.program import LOAD_MODES
from coach.core.registries.week import OVERRIDE_KINDS

type Table = Mapping[str, object]

WEEK_SHAPES = frozenset({"light_week", "minimum_week", "one_off_week"})
MINIMUM_WEEK_KEEPS = 2
# Both set the working load, so one line cannot carry the two.
LINE_CONFLICTS = (frozenset({"hold", "pin_load"}),)


def parse_plan_overrides(document: Table, *, file: str) -> tuple[PlanOverride, ...]:
    """The Draft's `[[override]]` array; scope is given by which refs are present."""
    top = Fields(document, file)
    return tuple(_override(fields) for fields in top.tables("override"))


def line_override(params: Table, *, where: str) -> PlanOverride:
    """An override Decision's `override = { kind, ...params }`, unscoped: the Decision's own
    session and exercise are the line."""
    f = Fields(params, where)
    kind = required(f.term("kind", OVERRIDE_KINDS, required=True))
    if OVERRIDE_KINDS.get(kind).scope != "line":
        raise f.wrong("kind", "a line-scope override")
    return f.done(PlanOverride(kind, params=_params(f, kind)))


def _override(f: Fields) -> PlanOverride:
    kind = required(f.term("kind", OVERRIDE_KINDS, required=True))
    scope = OVERRIDE_KINDS.get(kind).scope
    session = f.text("session", required=scope != "week")
    exercise = f.text("exercise", required=scope == "line")
    if scope == "week" and session is not None:
        raise f.wrong("session", f"absent: {kind} is a week override")
    if scope == "session" and exercise is not None:
        raise f.wrong("exercise", f"absent: {kind} is a session override")
    date = f.date("date", required=True) if kind == "add_session" else None
    return f.done(
        PlanOverride(
            kind,
            session_id=session,
            exercise_id=exercise,
            date=date,
            params=_params(f, kind),
            because=f.term("because", REASONS, required=True),
            text=f.text("text", required=True),
            evidence=tuple(str(ref) for ref in f.refs("evidence")),
        )
    )


def _params(f: Fields, kind: str) -> dict[str, object]:
    names = [n for n in OVERRIDE_KINDS.get(kind).params if n not in ("session", "date")]
    read = {name: _param(f, kind, name) for name in names}
    return {name: value for name, value in read.items() if value is not None}


def _param(f: Fields, kind: str, name: str) -> object | None:
    match name:
        case "keep":
            keep = f.texts("keep")
            if not 1 <= len(keep) <= MINIMUM_WEEK_KEEPS:
                raise f.wrong("keep", "one or two session ids")
            return keep
        case "location":
            return f.text(name)
        case "to" if kind == "move_session":
            return f.date(name, required=True)
        case "to":
            return f.text(name, required=True)
        case "load_mode":
            return f.term(name, LOAD_MODES)
        case "sets":
            return _set_groups(f)
        case "load":
            return f.number(name, required=True)
        case _:
            return f.number(name)


def _set_groups(f: Fields) -> tuple[SetGroup, ...]:
    value = f.raw("sets")
    if not isinstance(value, list) or not value:
        raise f.wrong("sets", "the line's whole set groups")
    groups = cast(list[object], value)
    if not all(isinstance(group, dict) for group in groups):
        raise f.wrong("sets", "an array of set group tables")
    return parse_set_groups(cast(Sequence[Table], groups), file=f.where, where="sets")


def override_conflicts(
    overrides: Iterable[PlanOverride], monday: datetime.date
) -> tuple[Flag, ...]:
    """`override_conflict` on every pair the precedence table forbids: two of one kind on one
    scope, two week shapes, and the line pairs that set one value twice."""
    return tuple(
        _flag(first, second, monday)
        for first, second in combinations(overrides, 2)
        if _conflict(first, second)
    )


def _conflict(first: PlanOverride, second: PlanOverride) -> bool:
    if {first.kind, second.kind} <= WEEK_SHAPES:
        return True
    if _scope(first) != _scope(second):
        return False
    return first.kind == second.kind or frozenset({first.kind, second.kind}) in LINE_CONFLICTS


def _scope(override: PlanOverride) -> tuple[object, ...]:
    return (
        OVERRIDE_KINDS.get(override.kind).scope,
        override.session_id,
        override.exercise_id,
        override.date,
    )


def _flag(first: PlanOverride, second: PlanOverride, monday: datetime.date) -> Flag:
    first_scope = OVERRIDE_KINDS.get(first.kind).scope
    if first_scope == "week" or OVERRIDE_KINDS.get(second.kind).scope == "week":
        scope = Scope("week", monday)
    elif first_scope == "session":
        scope = Scope("session", monday, session_id=first.session_id)
    else:
        scope = Scope("line", monday, session_id=first.session_id, exercise_id=first.exercise_id)
    kinds = [first.kind, second.kind]
    return raise_flag(
        "override_conflict",
        scope,
        {"kinds": kinds},
        f"{kinds[0]} and {kinds[1]} cannot stand together; remove one",
    )
