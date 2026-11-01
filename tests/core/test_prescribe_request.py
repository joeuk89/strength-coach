import dataclasses
import types
import typing

from coach.core import goal
from coach.core.prescription import PrescribeRequest

FORBIDDEN_FIELDS = {"week_plan", "plan", "goal", "phase", "weigh_in", "weigh_ins", "profile"}


def reachable(root: type) -> tuple[set[type], set[str]]:
    """Every class a request field's type names, through dataclasses and generics, and every
    field name on the way."""
    classes: set[type] = set()
    fields: set[str] = set()
    pending: list[object] = [root]
    while pending:
        hint = pending.pop()
        origin = typing.get_origin(hint)
        if origin is not None or isinstance(hint, types.UnionType):
            pending.extend(typing.get_args(hint))
            if isinstance(origin, type):
                pending.append(origin)
            continue
        if isinstance(hint, typing.TypeAliasType):
            pending.append(hint.__value__)
            continue
        if not isinstance(hint, type) or hint in classes:
            continue
        classes.add(hint)
        if dataclasses.is_dataclass(hint):
            hints = typing.get_type_hints(hint)
            fields.update(hints)
            pending.extend(hints.values())
    return classes, fields


def test_the_prescribe_request_holds_no_week_plan_goal_phase_or_weigh_in() -> None:
    classes, fields = reachable(PrescribeRequest)

    names = {cls.__name__ for cls in classes}
    assert not names & {"WeekPlan", "Goal", "PhaseOpen", "Phase", "WeighIn", "Profile"}
    assert not any(cls.__module__ == goal.__name__ for cls in classes)
    assert not fields & FORBIDDEN_FIELDS
    assert {"version", "exposures", "racks", "planned", "decisions"} <= fields
    assert {"ExposureSet", "SetGroup", "NiggleConstraint"} <= names
