"""Dose: fractional hard sets per muscle, delivered in a closed week or planned in a session,
and the plan warnings that read them (docs/spec/week.md, "Dose")."""

import datetime
from collections.abc import Iterable, Mapping, Sequence

from coach.core.closed_week.week import ClosedWeek
from coach.core.exposure import Exposure
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.muscles import DOSED_MUSCLES
from coach.core.planned_week import week_monday
from coach.core.prescription import LinePrescription, SessionPrescription
from coach.core.program.form import LiftDose

type MuscleMap = Mapping[str, Mapping[str, Sequence[str]]]

# A hard set is a working set above RPE 5 (rn:proximity-to-failure.5); an unstated RPE counts.
HARD_SET_RPE = 5
# rn:volume-frequency.2: direct 1, indirect 0.5.
INDIRECT_SHARE = 0.5
# rn:volume-frequency.3: about 11 fractional sets per muscle per session.
SESSION_CEILING = 11
# rn:volume-frequency.1; three of the trailing four ordinary weeks is opinion.
TRAILING_WEEKS = 4
UNDER_IN = 3
# rn:minimum-effective-dose.4: a priority lift keeps 2 hard sets in a disrupted week.
PRIORITY_FLOOR = 2


def is_hard(rpe: float | None) -> bool:
    return rpe is None or rpe > HARD_SET_RPE


def delivered_dose(
    exposures: Iterable[Exposure],
    muscles: MuscleMap,
    estimated: Iterable[Mapping[str, int]] = (),
) -> dict[str, float]:
    """`estimated` holds each trained coach-led session's estimated sets per muscle."""
    dose: dict[str, float] = {}
    for exposure in exposures:
        hard = sum(1 for s in exposure.working if is_hard(s.rpe))
        _add(dose, muscles.get(exposure.exercise_id), hard)
    for sets in estimated:
        for muscle, count in sets.items():
            dose[muscle] = dose.get(muscle, 0) + count
    return dose


def delivered_lift_dose(
    exposures: Iterable[Exposure], lifts: Mapping[str, LiftDose]
) -> dict[str, int]:
    """Each lift's hard sets with its counted variants', one per set."""
    hard: dict[str, int] = {}
    for exposure in exposures:
        hard[exposure.exercise_id] = hard.get(exposure.exercise_id, 0) + sum(
            1 for s in exposure.working if is_hard(s.rpe)
        )
    return {
        lift: sum(hard.get(exercise, 0) for exercise in (lift, *target.counts))
        for lift, target in lifts.items()
    }


def trailing_mean(weeks: Iterable[ClosedWeek], muscle: str) -> float | None:
    trailing = _trailing(weeks)
    if not trailing:
        return None
    return sum(w.dose.get(muscle, 0) for w in trailing) / len(trailing)


def dose_under_target(
    weeks: Iterable[ClosedWeek],
    monday: datetime.date,
    muscles: Sequence[str] = DOSED_MUSCLES,
) -> Flag | None:
    """The first muscle under target in three of the trailing four ordinary weeks."""
    trailing = [w for w in _trailing(weeks) if w.dose_target is not None]
    for muscle in muscles:
        figures = [w.dose.get(muscle, 0) for w in trailing]
        under = sum(1 for w, f in zip(trailing, figures, strict=True) if f < (w.dose_target or 0))
        if under >= UNDER_IN:
            target = trailing[-1].dose_target
            return raise_flag(
                "dose_under_target",
                Scope("week", monday),
                {"muscle": muscle, "target": target, "weekly_figures": figures},
                f"{muscle} was under its {target} hard sets in {under} of the last "
                f"{len(trailing)} ordinary weeks",
            )
    return None


def lift_dose_under_target(
    weeks: Iterable[ClosedWeek], monday: datetime.date, counted: Mapping[str, Sequence[str]]
) -> Flag | None:
    """The first lift under its target, its counted variants included, in three of the
    trailing four ordinary weeks that carried a target for it."""
    ordinary = _trailing(weeks)
    lifts = dict.fromkeys(lift for w in ordinary for lift in w.lift_dose_target)
    for lift in lifts:
        trailing = [w for w in ordinary if lift in w.lift_dose_target]
        figures = [w.lift_dose.get(lift, 0) for w in trailing]
        under = sum(
            1 for w, f in zip(trailing, figures, strict=True) if f < w.lift_dose_target[lift]
        )
        if under >= UNDER_IN:
            target = trailing[-1].lift_dose_target[lift]
            return raise_flag(
                "lift_dose_under_target",
                Scope("week", monday),
                {
                    "exercise_id": lift,
                    "target": target,
                    "weekly_figures": figures,
                    "counted": list(counted.get(lift, ())),
                },
                f"{lift} was under its {target} hard sets in {under} of the last "
                f"{len(trailing)} ordinary weeks",
                rn="rn:volume-frequency.1",
            )
    return None


def session_dose_high(session: SessionPrescription, muscles: MuscleMap) -> Flag | None:
    planned: dict[str, float] = {}
    for line in session.lines:
        _add(planned, muscles.get(line.exercise_id), _hard_sets(line))
    if not planned:
        return None
    muscle, sets = max(planned.items(), key=lambda item: item[1])
    if sets <= SESSION_CEILING:
        return None
    planned_session = session.session
    return raise_flag(
        "session_dose_high",
        Scope("session", week_monday(planned_session.date), session_id=planned_session.session_id),
        {"planned_sets": sets, "ceiling": SESSION_CEILING},
        f"{planned_session.session_id} plans {sets:g} fractional sets for {muscle}, over "
        f"{SESSION_CEILING}; move some to another session",
    )


def minimum_week_floor(
    sessions: Iterable[SessionPrescription],
    kept: Sequence[str],
    priority_lifts: Sequence[str],
    monday: datetime.date,
    counted: Mapping[str, Sequence[str]] | None = None,
) -> Flag | None:
    """`counted` names each lift's counted variants, whose planned hard sets count toward it."""
    hard: dict[str, int] = {}
    for session in sessions:
        for line in session.lines:
            hard[line.exercise_id] = hard.get(line.exercise_id, 0) + _hard_sets(line)
    for lift in priority_lifts:
        variants = (counted or {}).get(lift, ())
        if sum(hard.get(exercise, 0) for exercise in (lift, *variants)) < PRIORITY_FLOOR:
            return raise_flag(
                "minimum_week_floor",
                Scope("week", monday),
                {"priority_lift": lift, "kept_sessions": list(kept)},
                f"the minimum week keeps under {PRIORITY_FLOOR} hard sets of priority lift {lift}",
            )
    return None


def _trailing(weeks: Iterable[ClosedWeek]) -> list[ClosedWeek]:
    return sorted((w for w in weeks if w.ordinary), key=lambda w: w.monday)[-TRAILING_WEEKS:]


def _hard_sets(line: LinePrescription) -> int:
    return sum(g.count for g in line.groups if g.type == "working" and is_hard(_rpe(g.rpe)))


def _add(dose: dict[str, float], muscles: Mapping[str, Sequence[str]] | None, sets: float) -> None:
    if muscles is None or not sets:
        return
    for muscle in muscles.get("primary", ()):
        dose[muscle] = dose.get(muscle, 0) + sets
    for muscle in muscles.get("secondary", ()):
        dose[muscle] = dose.get(muscle, 0) + sets * INDIRECT_SHARE


def _rpe(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None
