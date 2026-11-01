"""A line's set groups as a `prescription` row freezes them (docs/spec/schema.md, "Week"):
`load` in athlete units for pages, `load_kg` the Hevy-bound value the Write plan hash covers."""

from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.config import Units
from coach.core.prescription import PrescribedGroup

type Json = dict[str, object]


def frozen_groups(groups: Sequence[PrescribedGroup], units: Units) -> list[Json]:
    return [_group(group, units) for group in groups]


def dose(groups: Sequence[Mapping[str, object]], units: Units) -> str:
    """The working groups as `4×6–8 at 125 lb`, the heaviest working load named once."""
    working = [g for g in groups if g.get("type") != "warm_up"]
    shape = " + ".join(_shape(g) for g in working) or "no working set"
    loads = [float(str(g["load"])) for g in working if g.get("load") is not None]
    return f"{shape} at {max(loads):g} {units}" if loads else shape


def _group(group: PrescribedGroup, units: Units) -> Json:
    document: Json = {"type": group.type, "count": group.count}
    if group.load is not None:
        document |= {"load": group.load.amount, "load_kg": group.load.hevy_kg(units)}
    if isinstance(group.reps, tuple):
        document["range"] = list(group.reps)
    elif group.reps is not None:
        document["reps"] = group.reps
    optional = {"duration_s": group.duration_s, "rpe": group.rpe, "rpe_cap": group.rpe_cap}
    return document | {key: value for key, value in optional.items() if value is not None}


def _shape(group: Mapping[str, object]) -> str:
    count = group["count"]
    rep_range = group.get("range")
    if isinstance(rep_range, list):
        low, high = cast(list[int], rep_range)
        return f"{count}×{low}–{high}"
    if group.get("reps") is not None:
        return f"{count}×{group['reps']}"
    return f"{count}×{group.get('duration_s')} s"
