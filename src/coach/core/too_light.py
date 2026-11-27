"""A line too light (docs/spec/prescription.md, "A line too light"): the anchor's logged RPE far
under the authored, or the e1RM's load for the authored dose more than one rack row above the
prescribed load. The warning suggests one load; the rule never moves the line by it."""

from collections.abc import Iterable
from dataclasses import dataclass

from coach.core.ceilings import fewest_reps, most_reps
from coach.core.closed_week.against import ROUNDING, LineAgainst, TargetSet
from coach.core.e1rm import PRECISION, E1rm, model_load
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.load import Load
from coach.core.program.form import Line, Number
from coach.core.rack import Rack, next_row_up, round_to_rack
from coach.core.rpe_gap import RPE_GAP

SCHEMES = ("double_progression", "linear", "top_backoff")


@dataclass(frozen=True)
class TooLight:
    """`suggested` is None when the line has no e1RM to model a load from."""

    flag: Flag
    suggested: Load | None


def too_light(
    line: Line,
    anchor: Exposure,
    prescribed: Load,
    *,
    e1rm: E1rm | None,
    exposures: Iterable[Exposure],
    rack: Rack,
    safety_ceiling: Number | None,
    scope: Scope,
) -> TooLight | None:
    """`prescribed` is the scheme's load on the rack, before any cut or ceiling."""
    if line.scheme.name not in SCHEMES:
        return None
    gap = _mean_rpe_gap(line, anchor)
    model = _model(line, e1rm, prescribed)
    nearest = None if model is None else round_to_rack(rack, model, "step_up").load
    one_row = next_row_up(rack, prescribed).load
    light_by_rpe = gap is not None and gap <= -RPE_GAP + ROUNDING
    light_by_model = nearest is not None and nearest.amount > one_row.amount
    if not (light_by_rpe or light_by_model):
        return None
    suggested = nearest
    if suggested is not None and safety_ceiling is not None:
        limit = round_to_rack(rack, Load(safety_ceiling, suggested.mode), "cut").load
        suggested = min(suggested, limit, key=lambda load: load.amount)
    source = _source(e1rm, exposures)
    params: dict[str, object] = {
        "anchor_exposure": anchor.ref,
        "logged_sets": [
            {
                "load": None if s.load is None else _amount(s.load.as_mode(prescribed.mode)),
                "reps": s.reps,
                "rpe": s.rpe,
            }
            for s in anchor.working
        ],
        "rpe_gap": gap,
        "e1rm": None if e1rm is None else _amount(e1rm.load.as_mode(prescribed.mode)),
        "e1rm_exposure": None if e1rm is None else e1rm.exposure,
        "e1rm_date": None if source is None else source.date.isoformat(),
        "e1rm_session": None if source is None else source.session_id,
        "model_load": None if model is None else model.amount,
        "suggested_load": None if suggested is None else suggested.amount,
    }
    message = _message(gap, light_by_rpe, model, source, prescribed, suggested)
    return TooLight(raise_flag("load_too_light", scope, params, message), suggested)


def _mean_rpe_gap(line: Line, anchor: Exposure) -> float | None:
    """The mean of logged minus authored RPE over the anchor's working sets paired in order with
    the authored ones, counting only pairs that carry both. None on an anchor from a week a
    return band capped the line's RPE under the authored."""
    if anchor.match is not None and line.exercise in anchor.match.return_band_lines:
        return None
    targets = tuple(
        TargetSet(fewest_reps(group.reps), None if group.rpe is None else float(group.rpe))
        for group in line.working_groups()
        for _ in range(group.count)
    )
    offs = [
        off
        for off in LineAgainst(line.exercise, "logged", targets, anchor.working).rpe_off
        if off is not None
    ]
    return round(sum(offs) / len(offs), PRECISION) if offs else None


def _model(line: Line, e1rm: E1rm | None, prescribed: Load) -> Load | None:
    """The e1RM's load for the top working group's most reps at its RPE: on a range, the top,
    which is the scheme's own hit, so a line held on a missed rep is not read as too light."""
    groups = line.working_groups()
    if e1rm is None or not groups:
        return None
    reps, rpe = most_reps(groups[0].reps), groups[0].rpe
    if not reps or rpe is None:
        return None
    return model_load(e1rm.load.as_mode(prescribed.mode), reps, float(rpe))


def _source(e1rm: E1rm | None, exposures: Iterable[Exposure]) -> Exposure | None:
    if e1rm is None:
        return None
    return next((e for e in exposures if e.ref == e1rm.exposure), None)


def _message(
    gap: float | None,
    light_by_rpe: bool,
    model: Load | None,
    source: Exposure | None,
    prescribed: Load,
    suggested: Load | None,
) -> str:
    parts: list[str] = []
    if light_by_rpe and gap is not None:
        parts.append(f"the anchor's sets averaged {-gap:g} RPE under the authored")
    if model is not None and source is not None:
        where = "" if source.session_id is None else f", {source.session_id}"
        parts.append(
            f"the e1RM from {source.date.isoformat()}{where} gives {model.amount:g} "
            "for the authored dose"
        )
    tail = "" if suggested is None else f", suggested {suggested.amount:g}"
    return f"{'; '.join(parts)}: the line prescribes {prescribed.amount:g}{tail}"


def _amount(load: Load) -> float:
    return round(load.amount, PRECISION)
