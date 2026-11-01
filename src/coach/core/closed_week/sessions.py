"""What each planned session of a closed week counted as: trained or not, which denominators it
sits in and whether it passed the session gate (docs/spec/week.md, "Session kinds in the week"
and "The session gate")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from coach.core.closed_week.match import PlannedRef, WeekWorkout
from coach.core.exposure import ExposureSet
from coach.core.prescription import PlannedSession, StatusSpan

GATE_KINDS = ("lifting", "coach_led")
# rn:deloads.11: two thirds of the prescribed working sets, mean RPE no more than 1.5 under.
GATE_SET_SHARE = 2 / 3
GATE_RPE_SLACK = 1.5
# The tolerance a mean of tenths carries; a mean exactly 1.5 under still passes.
ROUNDING = 1e-9


@dataclass(frozen=True)
class TargetSet:
    """One prescribed working set: the bottom of its reps and its RPE."""

    reps: int | None = None
    rpe: float | None = None


@dataclass(frozen=True)
class PlannedWork:
    """A planned session with its prescribed working sets by exercise; a `hold` line is not
    among them. A dropped core session stays in the week as a Miss and takes no workout."""

    session: PlannedSession
    targets: Mapping[str, tuple[TargetSet, ...]] = field(
        default_factory=dict[str, tuple[TargetSet, ...]]
    )
    dropped: bool = False

    @property
    def ref(self) -> PlannedRef:
        return (self.session.date, self.session.session_id)

    @property
    def prescribed_sets(self) -> int:
        return sum(len(sets) for sets in self.targets.values())


@dataclass(frozen=True)
class AgainstPrescription:
    reps_missed: int = 0
    effort_off: int = 0
    rpe_missing: int = 0


@dataclass(frozen=True)
class SessionOutcome:
    work: PlannedWork
    trained: bool
    in_gate: bool
    in_adherence: bool
    passed: bool | None
    workout_id: str | None = None
    against: AgainstPrescription | None = None
    cancelled: bool = False
    rested: bool = False

    @property
    def session(self) -> PlannedSession:
        return self.work.session


def session_outcome(
    work: PlannedWork,
    *,
    workout: WeekWorkout | None,
    trained_unlogged: bool = False,
    cancelled: bool = False,
    spans: Sequence[StatusSpan] = (),
) -> SessionOutcome:
    session = work.session
    trained = workout is not None or trained_unlogged
    on_span = any(span.covers(session.date) for span in spans)
    excluded = cancelled or (on_span and not trained)
    core = session.tier == "core" and not excluded
    coach_led = session.kind == "coach_led"
    in_gate = core and session.kind in GATE_KINDS and (coach_led or work.prescribed_sets > 0)
    pairs = _pairs(work, workout)
    passed: bool | None = None
    if in_gate:
        passed = trained if coach_led else trained and _passes(work, pairs)
    return SessionOutcome(
        work,
        trained,
        in_gate,
        core,
        passed,
        None if workout is None else workout.id,
        _against(pairs) if workout is not None and not coach_led else None,
        cancelled,
        on_span and not trained,
    )


def _pairs(work: PlannedWork, workout: WeekWorkout | None) -> list[tuple[ExposureSet, TargetSet]]:
    if workout is None:
        return []
    logged = {e.exercise_id: e.working for e in workout.exposures}
    return [
        pair
        for exercise, targets in work.targets.items()
        for pair in zip(logged.get(exercise, ()), targets, strict=False)
    ]


def _passes(work: PlannedWork, pairs: list[tuple[ExposureSet, TargetSet]]) -> bool:
    if len(pairs) < GATE_SET_SHARE * work.prescribed_sets - ROUNDING:
        return False
    prescribed = [t.rpe for sets in work.targets.values() for t in sets if t.rpe is not None]
    rated = [(s.rpe if s.rpe is not None else t.rpe) for s, t in pairs if t.rpe is not None]
    if not prescribed or not rated:
        return True
    shortfall = sum(prescribed) / len(prescribed) - sum(rated) / len(rated)
    return shortfall <= GATE_RPE_SLACK + ROUNDING


def _against(pairs: list[tuple[ExposureSet, TargetSet]]) -> AgainstPrescription:
    return AgainstPrescription(
        reps_missed=sum(
            1 for s, t in pairs if t.reps is not None and s.reps is not None and s.reps < t.reps
        ),
        effort_off=sum(
            1
            for s, t in pairs
            if s.rpe is not None
            and t.rpe is not None
            and abs(s.rpe - t.rpe) >= GATE_RPE_SLACK - ROUNDING
        ),
        rpe_missing=sum(1 for s, _ in pairs if s.rpe is None),
    )
