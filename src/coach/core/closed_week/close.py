"""One closed week from its facts: Match, each session as it counted, the week's kind and its
delivered dose (docs/spec/week.md; ADR 0010, "What each kind's workout yields")."""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from coach.core.closed_week.dose import (
    HARD_SET_RPE,
    MuscleMap,
    delivered_dose,
    delivered_lift_dose,
)
from coach.core.closed_week.kind import week_kind
from coach.core.closed_week.match import PlannedRef, WeekWorkout, match_week
from coach.core.closed_week.sessions import PlannedWork, session_outcome
from coach.core.closed_week.week import ClosedWeek
from coach.core.exposure import Exposure
from coach.core.prescription import PlannedSession, StatusSpan
from coach.core.program.form import LiftDose

# A matched workout of these kinds yields no Exposures for the dose; coach-led counts its
# estimated sets instead.
NO_DOSE_KINDS = ("conditioning", "practice", "coach_led")


@dataclass(frozen=True)
class WeekFacts:
    """`claims` maps a workout to the planned session a `match` Annotation or a manual
    coach-led workout names; `carried` the week overrides of the plan in force; `estimated`
    each coach-led session's estimated sets per muscle; `lift_dose` the per-lift targets and
    counted variants of the version in force."""

    monday: datetime.date
    planned: tuple[PlannedWork, ...] = ()
    workouts: tuple[WeekWorkout, ...] = ()
    routines: Mapping[str, str] = field(default_factory=dict[str, str])
    claims: Mapping[str, PlannedRef] = field(default_factory=dict[str, PlannedRef])
    trained_unlogged: frozenset[PlannedRef] = frozenset()
    cancelled: frozenset[PlannedRef] = frozenset()
    spans: tuple[StatusSpan, ...] = ()
    carried: frozenset[str] = frozenset()
    returned: bool = False
    muscles: MuscleMap = field(default_factory=dict[str, Mapping[str, list[str]]])
    estimated: Mapping[str, Mapping[str, int]] = field(default_factory=dict[str, Mapping[str, int]])
    dose_target: int | None = None
    lift_dose: Mapping[str, LiftDose] = field(default_factory=dict[str, LiftDose])


def close_week(facts: WeekFacts) -> ClosedWeek:
    matchable = [work.session for work in facts.planned if not work.dropped]
    matches = match_week(matchable, facts.workouts, routines=facts.routines, claims=facts.claims)
    by_workout = {w.id: w for w in facts.workouts}
    taken = {(s.date, s.session_id): by_workout[w] for w, s in matches.items()}
    sessions = tuple(
        session_outcome(
            work,
            workout=taken.get(work.ref),
            trained_unlogged=work.ref in facts.trained_unlogged,
            cancelled=work.ref in facts.cancelled,
            spans=facts.spans,
        )
        for work in facts.planned
    )
    exposures = _dosed_exposures(facts, matches)
    estimated = [
        facts.estimated.get(s.session.session_id, {})
        for s in sessions
        if s.session.kind == "coach_led" and s.trained
    ]
    return ClosedWeek(
        facts.monday,
        week_kind(sessions, carried=facts.carried, returned=facts.returned),
        sessions,
        delivered_dose(exposures, facts.muscles, estimated),
        facts.dose_target,
        delivered_lift_dose(exposures, facts.lift_dose),
        {lift: target.sets for lift, target in facts.lift_dose.items()},
    )


def _dosed_exposures(facts: WeekFacts, matches: Mapping[str, PlannedSession]) -> list[Exposure]:
    kinds = {w: s.kind for w, s in matches.items()}
    return [
        _rated_only(exposure) if kinds.get(workout.id) == "rehab" else exposure
        for workout in facts.workouts
        if workout.kind == "lifting" and kinds.get(workout.id) not in NO_DOSE_KINDS
        for exposure in workout.exposures
    ]


def _rated_only(exposure: Exposure) -> Exposure:
    """A rehab set counts toward the dose only when logged above the hard-set RPE (ADR 0010)."""
    kept = tuple(
        s
        for s in exposure.sets
        if s.set_type != "working" or (s.rpe is not None and s.rpe > HARD_SET_RPE)
    )
    return replace(exposure, sets=kept)
