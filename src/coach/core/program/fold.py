"""A WeekPlan's line overrides folded into the version in force as an `amend` Draft
(docs/spec/overrides.md, "What `--apply-plan` folds")."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import cast

from coach.core.prescription import PlanOverride
from coach.core.program.form import Line, Number, ProgramForm, SchemeRef, Session, SetGroup

# The order a line's overrides fold in: the swap names the exercise the rest apply to.
FOLDING = ("swap_exercise", "restate_sets", "hold", "pin_load", "drop_line")
# An exercise_ladder's rungs carry its exercises and sets; the Draft's rungs are edited by hand.
RUNGS_CARRY = ("swap_exercise", "restate_sets")


@dataclass(frozen=True)
class Folded:
    session_id: str
    exercise_id: str
    kind: str


@dataclass(frozen=True)
class FoldedForm:
    form: ProgramForm
    folded: tuple[Folded, ...]
    pins: frozenset[tuple[str, str]]


def fold_overrides(form: ProgramForm, overrides: Sequence[PlanOverride]) -> FoldedForm:
    """Session and week kinds never fold: a dropped session is parked by Decision or removed
    by hand in the Draft."""
    folding = sorted(
        (o for o in overrides if o.kind in FOLDING), key=lambda o: FOLDING.index(o.kind)
    )
    folded: list[Folded] = []
    applied: list[PlanOverride] = []
    sessions: list[Session] = []
    for session in form.sessions:
        lines: list[Line] = []
        for line in session.lines:
            on_line = [
                o
                for o in folding
                if (o.session_id, o.exercise_id) == (session.id, line.exercise)
                and not (line.scheme.ladder and o.kind in RUNGS_CARRY)
            ]
            folded.extend(Folded(session.id, line.exercise, o.kind) for o in on_line)
            applied.extend(on_line)
            current: Line | None = line
            for override in on_line:
                current = None if current is None else _fold(current, override)
            if current is not None:
                lines.append(current)
        sessions.append(replace(session, lines=tuple(lines)))
    pins = frozenset(
        (f.session_id, _exercise_after(f, applied)) for f in folded if f.kind == "pin_load"
    )
    return FoldedForm(replace(form, kind="amend", sessions=tuple(sessions)), tuple(folded), pins)


def _exercise_after(pin: Folded, folding: Sequence[PlanOverride]) -> str:
    """A pin on a swapped line labels the exercise the swap put there."""
    swap = next(
        (
            o
            for o in folding
            if o.kind == "swap_exercise"
            and (o.session_id, o.exercise_id) == (pin.session_id, pin.exercise_id)
        ),
        None,
    )
    return pin.exercise_id if swap is None else str(swap.params["to"])


def _fold(line: Line, override: PlanOverride) -> Line | None:
    params = override.params
    match override.kind:
        case "swap_exercise":
            return replace(
                line,
                exercise=str(params["to"]),
                load_mode=cast(str | None, params.get("load_mode", line.load_mode)),
                start_load=_load(params.get("start_load")),
            )
        case "restate_sets":
            return replace(line, sets=cast(tuple[SetGroup, ...], params["sets"]))
        case "hold":
            return replace(line, scheme=SchemeRef("hold"))
        case "pin_load":
            return replace(line, start_load=_load(params["load"]))
        case _:
            return None


def _load(value: object) -> Number | None:
    """A whole load folds as it was authored, 100 rather than 100.0."""
    if value is None:
        return None
    load = cast(float, value)
    return int(load) if load.is_integer() else load
