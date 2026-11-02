"""What adopt fills from the emphasis and the Phase (docs/spec/goals.md, "Defaults per
emphasis" and "What the Phase changes"). Nothing else on the form is ever filled."""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from coach.core.program.form import Deload, Dose, Emphasis, LiftDose, ProgramForm, Session
from coach.core.registries.phase import PHASE

PER_MUSCLE = 10
PER_LIFT = 8
# A surplus moves the dose to the bottom of the upper half of each band: 10-20 and 5-15.
UPPER_HALF = {"per_muscle": 15, "per_lift": 10}
MAINTENANCE_SHARE = 3
HARD_WEEKS_CEILING = 6

DELOADS: dict[Emphasis, Deload] = {
    "hypertrophy": Deload(HARD_WEEKS_CEILING, 40, 0, 8, True),
    "strength": Deload(HARD_WEEKS_CEILING, 30, 0, 8, True),
    "maintenance": Deload(HARD_WEEKS_CEILING, 0, 0, 8, False),
}


@dataclass(frozen=True)
class Filled:
    """The filled form and the paths of what was filled, for the dry run's diff."""

    form: ProgramForm
    filled: tuple[str, ...]


def fill(
    form: ProgramForm,
    *,
    priority_lifts: Sequence[str],
    phase: str | None,
    session_minutes: int,
) -> Filled:
    filled: list[str] = []
    dose = form.dose
    if dose is None:
        dose = default_dose(form.emphasis, priority_lifts, phase)
        filled.append("dose")
    deload = form.deload
    if deload is None:
        deload = DELOADS[form.emphasis]
        filled.append("deload")
    sessions: list[Session] = []
    for session in form.sessions:
        if session.kind == "lifting" and session.minutes is None:
            session = replace(session, minutes=session_minutes)
            filled.append(f"session.{session.id}.minutes")
        sessions.append(session)
    form = replace(form, dose=dose, deload=deload, sessions=tuple(sessions))
    return Filled(form, tuple(filled))


def default_dose(emphasis: Emphasis, priority_lifts: Sequence[str], phase: str | None) -> Dose:
    per_muscle, per_lift = PER_MUSCLE, PER_LIFT
    if emphasis == "maintenance":
        per_muscle = math.ceil(per_muscle / MAINTENANCE_SHARE)
        per_lift = math.ceil(per_lift / MAINTENANCE_SHARE)
    elif phase is not None and PHASE.get(phase).dose_default == "upper_half_of_band":
        per_muscle, per_lift = UPPER_HALF["per_muscle"], UPPER_HALF["per_lift"]
    return Dose(per_muscle, {lift: LiftDose(per_lift) for lift in priority_lifts})
