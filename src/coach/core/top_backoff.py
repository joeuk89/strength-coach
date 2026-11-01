"""`top_backoff` (docs/spec/prescription.md, "The move, per scheme"): the top set from the e1RM
model, capped at one rack row above the anchor's top; back-offs at `pct_of_top` of it."""

from dataclasses import dataclass

from coach.core.e1rm import load_for
from coach.core.load import Load
from coach.core.program.form import Line
from coach.core.rack import Rack, next_row_up, round_to_rack
from coach.core.scheme_params import number

PRECISION = 4


@dataclass(frozen=True)
class TopSet:
    load: Load
    cause: str


def top_set(e1rm: Load, line: Line, anchor_top: Load, rack: Rack) -> TopSet:
    top_group = line.working_groups()[0]
    assert isinstance(top_group.reps, int) and top_group.rpe is not None
    model = load_for(e1rm, top_group.reps, float(top_group.rpe), rack)
    cap = next_row_up(rack, anchor_top).load
    if model.amount > cap.amount:
        return TopSet(cap, "one_row_cap")
    return TopSet(model, "e1rm")


def back_off_load(top: Load, line: Line, rack: Rack | None) -> Load:
    target = Load(round(top.amount * number(line.scheme, "pct_of_top") / 100, PRECISION), top.mode)
    return target if rack is None else round_to_rack(rack, target, "step_up").load
