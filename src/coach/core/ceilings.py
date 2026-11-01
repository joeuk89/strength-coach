"""Steps 5 to 7: niggle constraints, RPE ceilings and the safety ceiling (docs/spec/
prescription.md). Ceilings bind by the strictest and never compose (ADR 0017)."""

import datetime
import math
from collections.abc import Iterable, Sequence
from dataclasses import replace

from coach.core.e1rm import MAX_REPS_TO_FAILURE
from coach.core.exposure import Exposure
from coach.core.load import Load, LoadMode
from coach.core.prescription import DecisionInForce, NiggleConstraint, StatusSpan
from coach.core.program.form import Number, Reps, SetGroup

ILLNESS_RPE_CAP = 7
ILLNESS_RPE_CAP_RN = "rn:detraining-return.4"


def easier(a: Load, b: Load) -> Load:
    """The lighter dose: under assistance, the one with more assistance."""
    if a.mode == "assisted":
        return a if a.amount >= b.amount else b
    return a if a.amount <= b.amount else b


def harder(a: Load, b: Load) -> bool:
    """Whether `a` is a heavier dose than `b`."""
    return a.amount < b.amount if a.mode == "assisted" else a.amount > b.amount


def constraints_on(
    constraints: Iterable[NiggleConstraint], exercise_id: str, pattern: str | None
) -> tuple[NiggleConstraint, ...]:
    """The rows that reach a line: its exercise, its pattern, or global."""
    return tuple(
        c
        for c in constraints
        if c.exercise_id == exercise_id
        or (c.pattern is not None and c.pattern == pattern)
        or (c.exercise_id is None and c.pattern is None)
    )


def niggle_load_caps(
    constraints: Iterable[NiggleConstraint], *, mode: LoadMode, anchor_top: Load | None
) -> tuple[tuple[Load, NiggleConstraint], ...]:
    caps: list[tuple[Load, NiggleConstraint]] = []
    for c in constraints:
        if c.kind == "load_cap" and c.value is not None:
            caps.append((Load(c.value, mode), c))
        elif c.kind == "no_added_load" and anchor_top is not None:
            caps.append((anchor_top, c))
    return tuple(caps)


def ill_since(
    spans: Iterable[StatusSpan],
    exposures: Iterable[Exposure],
    *,
    exercise_id: str,
    anchor_date: datetime.date,
    on: datetime.date,
) -> bool:
    """An `ill` span since the anchor with no exposure of the lift after it ended."""
    later = [e.date for e in exposures if e.exercise_id == exercise_id and e.date < on]
    for span in spans:
        if span.kind != "ill" or span.from_date >= on:
            continue
        ended = span.to_date or on
        if ended >= anchor_date and not any(day > ended for day in later):
            return True
    return False


def safety_ceiling(decisions: Iterable[DecisionInForce], exercise_id: str) -> Number | None:
    for decision in decisions:
        load = decision.params.get("load")
        if (
            decision.kind == "safety_ceiling"
            and decision.exercise_id == exercise_id
            and isinstance(load, int | float)
        ):
            return load
    return None


def fewest_reps(reps: Reps | None) -> int | None:
    if isinstance(reps, tuple):
        return reps[0]
    if isinstance(reps, str):
        return int(reps.rstrip("+"))
    return reps


def most_reps(reps: Reps | None) -> int:
    if isinstance(reps, tuple):
        return reps[1]
    if isinstance(reps, str):
        return int(reps.rstrip("+"))
    return reps or 0


def reps_within_model(sets: Sequence[SetGroup], cap: Number) -> tuple[SetGroup, ...]:
    """Reps cut so no capped set implies more than 12 reps to failure (rn:autoregulation.5)."""
    most = math.floor(MAX_REPS_TO_FAILURE - 10 + cap)
    return tuple(replace(g, reps=_at_most(g.reps, most)) if g.working else g for g in sets)


def _at_most(reps: Reps | None, most: int) -> Reps | None:
    if isinstance(reps, tuple):
        low, high = min(reps[0], most), min(reps[1], most)
        return low if low == high else (low, high)
    if isinstance(reps, int):
        return min(reps, most)
    return reps
