"""A line's working groups in the words the routine note uses, frozen shape in, text out."""

from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.frozen_prescription import group_shape


def working_shape(working: Sequence[Mapping[str, object]]) -> str:
    """`2×5 + 5+ (stop at RPE 9)`."""
    return " + ".join(_shape(g) for g in working) or "no working set"


def working_rpe(working: Sequence[Mapping[str, object]]) -> str:
    """` @8` where the working groups agree on one RPE, otherwise nothing."""
    rpes = {g.get("rpe") for g in working} - {None}
    return f" @{float(cast(float, rpes.pop())):g}" if len(rpes) == 1 else ""


def _shape(group: Mapping[str, object]) -> str:
    reps = group.get("reps")
    if not isinstance(reps, str):
        return group_shape(group)
    count = group["count"]
    shape = reps if count == 1 else f"{count}×{reps}"
    cap = group.get("rpe_cap")
    return shape if cap is None else f"{shape} (stop at RPE {float(cast(float, cap)):g})"
