"""The plan warnings that read a line against the e1RM model (docs/spec/validation.md;
rn:autoregulation.5 and .6)."""

from collections.abc import Sequence

from coach.core.ceilings import fewest_reps
from coach.core.e1rm import (
    LOAD_BEARING,
    MAX_REPS_TO_FAILURE,
    E1rm,
    implied_rpe,
    model_load,
    most_reps_over_cap,
    reps_to_failure,
)
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.prescription import PrescribedGroup
from coach.core.program.form import Line, Reps

UNEARNED_RPE = 10.5
UNEARNED_RPE_RN = "rn:autoregulation.6"


def top_set_above_e1rm(
    groups: Sequence[PrescribedGroup], found: E1rm | None, scope: Scope
) -> Flag | None:
    """The working group whose load implies the highest RPE at its fewest reps, when that RPE is
    past 10.5. A lower-bound e1RM cannot show a load beyond failure, so it raises nothing."""
    if found is None or found.lower_bound:
        return None
    judged = [
        (implied_rpe(found.load, group.load, reps), group, reps)
        for group in groups
        if group.type == "working"
        and group.load is not None
        and group.load.mode in LOAD_BEARING
        and (reps := fewest_reps(group.reps)) is not None
    ]
    if not judged:
        return None
    rpe, group, reps = max(judged, key=lambda judged: judged[0])
    if rpe <= UNEARNED_RPE:
        return None
    assert group.load is not None
    e1rm = found.load.as_mode(group.load.mode)
    target = None if group.rpe is None else float(group.rpe)
    model = None if target is None else model_load(e1rm, reps, target).amount
    return raise_flag(
        "top_set_above_e1rm",
        scope,
        {"e1rm": e1rm.amount, "model": model, "load": group.load.amount, "rpe_target": group.rpe},
        f"{reps} reps at {group.load.amount:g} implies RPE {rpe:g} on the e1RM of "
        f"{e1rm.amount:g}: past failure",
    )


def over_rep_cap(line: Line, anchor: Exposure) -> Flag | None:
    """The anchor's sets the cap kept out of the e1RM, on a line authored inside the cap: a line
    authored past it never expects an estimate from its own logs."""
    if any(
        _authored_to_failure(g.reps, g.rpe) > MAX_REPS_TO_FAILURE for g in line.working_groups()
    ):
        return None
    reps = most_reps_over_cap(anchor)
    if reps is None:
        return None
    return raise_flag(
        "over_rep_cap",
        Scope("exposure", workout_id=anchor.workout_id, exercise_id=anchor.exercise_id),
        {"reps": reps, "cap": MAX_REPS_TO_FAILURE},
        f"{anchor.ref} logged a set {reps:g} reps from failure, past the cap of "
        f"{MAX_REPS_TO_FAILURE}: it gives no e1RM",
    )


def _authored_to_failure(reps: Reps | None, rpe: float | None) -> float:
    if isinstance(reps, tuple):
        most = reps[1]
    elif isinstance(reps, str):
        most = int(reps.rstrip("+"))
    else:
        most = reps or 0
    return reps_to_failure(most, rpe)
