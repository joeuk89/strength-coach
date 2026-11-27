"""What each planned session of a closed week counted as: trained or not, which denominators it
sits in and whether it passed the session gate (docs/spec/week.md, "Session kinds in the week"
and "The session gate")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from coach.core.closed_week.against import (
    AgainstPrescription,
    LineAgainst,
    TargetSet,
    against,
    lines_against,
)
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
class PlannedWork:
    """A planned session with its prescribed working sets by exercise in plan order; `held`
    names the `hold` lines among them. A dropped core session stays in the week as a Miss and
    takes no workout. `returned` names the lines that took a return band."""

    session: PlannedSession
    targets: Mapping[str, tuple[TargetSet, ...]] = field(
        default_factory=dict[str, tuple[TargetSet, ...]]
    )
    dropped: bool = False
    returned: frozenset[str] = frozenset()
    held: frozenset[str] = frozenset()

    @property
    def scheme_targets(self) -> Mapping[str, tuple[TargetSet, ...]]:
        """The lines a scheme moves: every line but a `hold` one."""
        return {e: sets for e, sets in self.targets.items() if e not in self.held}

    @property
    def ref(self) -> PlannedRef:
        return (self.session.date, self.session.session_id)

    @property
    def prescribed_sets(self) -> int:
        return sum(len(sets) for sets in self.scheme_targets.values())


@dataclass(frozen=True)
class SessionOutcome:
    work: PlannedWork
    trained: bool
    in_gate: bool
    in_adherence: bool
    passed: bool | None
    workout_id: str | None = None
    lines: tuple[LineAgainst, ...] = ()
    cancelled: bool = False
    rested: bool = False

    @property
    def session(self) -> PlannedSession:
        return self.work.session

    @property
    def against(self) -> AgainstPrescription | None:
        """The counts the card shows: none for an untrained or coach-led session."""
        if self.workout_id is None or self.session.kind == "coach_led":
            return None
        return against(self.lines)


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
    lines = lines_against(work.targets, work.held, workout)
    pairs = [pair for line in lines if not line.hold for pair in line.pairs]
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
        lines,
        cancelled,
        on_span and not trained,
    )


def _passes(work: PlannedWork, pairs: list[tuple[ExposureSet, TargetSet]]) -> bool:
    if len(pairs) < GATE_SET_SHARE * work.prescribed_sets - ROUNDING:
        return False
    prescribed = [t.rpe for sets in work.scheme_targets.values() for t in sets if t.rpe is not None]
    rated = [(s.rpe if s.rpe is not None else t.rpe) for s, t in pairs if t.rpe is not None]
    if not prescribed or not rated:
        return True
    shortfall = sum(prescribed) / len(prescribed) - sum(rated) / len(rated)
    return shortfall <= GATE_RPE_SLACK + ROUNDING
