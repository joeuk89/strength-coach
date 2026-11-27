"""What each planned session of a closed week counted as: trained or not, which denominators it
sits in and whether it passed the session gate (docs/spec/week.md, "Session kinds in the week"
and "The session gate")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from coach.core.closed_week.against import (
    EFFORT_OFF_RPE,
    ROUNDING,
    AgainstPrescription,
    LineAgainst,
    TargetSet,
    against,
    lines_against,
)
from coach.core.closed_week.match import PlannedRef, WeekWorkout, in_start_order
from coach.core.exposure import ExposureSet
from coach.core.flag import Flag, Scope, raise_flag
from coach.core.planned_week import week_monday
from coach.core.prescription import PlannedSession, StatusSpan

GATE_KINDS = ("lifting", "coach_led")
# rn:deloads.11: two thirds of the prescribed working sets, mean RPE no more than 1.5 under.
GATE_SET_SHARE = 2 / 3
# Opinion: under a third of the prescribed working sets logged, a matched session may not have
# counted, so the athlete is asked.
NEAR_EMPTY_SET_SHARE = 1 / 3


@dataclass(frozen=True)
class PlannedWork:
    """A planned session with its prescribed working sets by exercise in plan order; `held`
    names the `hold` lines among them. A dropped core session stays in the week as a Miss and
    takes no workout. `returned` names the lines that took a return band; `lines` every frozen
    exercise of the session, `hold` lines included, which Match reads."""

    session: PlannedSession
    targets: Mapping[str, tuple[TargetSet, ...]] = field(
        default_factory=dict[str, tuple[TargetSet, ...]]
    )
    dropped: bool = False
    returned: frozenset[str] = frozenset()
    held: frozenset[str] = frozenset()
    lines: frozenset[str] = frozenset()

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
    """`workouts` are every workout matched to the session, in start-time order; a
    `miss_tagged` session is untrained whatever it holds."""

    work: PlannedWork
    trained: bool
    in_gate: bool
    in_adherence: bool
    passed: bool | None
    workouts: tuple[WeekWorkout, ...] = ()
    lines: tuple[LineAgainst, ...] = ()
    cancelled: bool = False
    rested: bool = False
    miss_tagged: bool = False

    @property
    def session(self) -> PlannedSession:
        return self.work.session

    @property
    def workout_ids(self) -> tuple[str, ...]:
        return tuple(w.id for w in self.workouts)

    @property
    def against(self) -> AgainstPrescription | None:
        """The counts the card shows: none for an untrained or coach-led session."""
        if not self.workouts or self.session.kind == "coach_led":
            return None
        return against(self.lines)

    @property
    def sets_logged(self) -> int:
        """The logged working sets paired with a prescribed one, as the gate counts them."""
        return sum(len(line.pairs) for line in self.lines if not line.hold)

    @property
    def sets_prescribed(self) -> int:
        return self.work.prescribed_sets

    @property
    def near_empty(self) -> bool:
        return (
            self.session.tier == "core"
            and bool(self.workouts)
            and self.sets_prescribed > 0
            and self.sets_logged < NEAR_EMPTY_SET_SHARE * self.sets_prescribed - ROUNDING
        )


def session_near_empty(outcome: SessionOutcome) -> Flag | None:
    """Raised until the athlete answers it with a `miss_tag`; with no answer the session stays
    trained."""
    if not outcome.near_empty or outcome.miss_tagged or outcome.cancelled:
        return None
    session = outcome.session
    return raise_flag(
        "session_near_empty",
        Scope("session", week_monday(session.date), session_id=session.session_id),
        {
            "date": session.date.isoformat(),
            "sets_logged": outcome.sets_logged,
            "sets_prescribed": outcome.sets_prescribed,
        },
        f"{session.session_id} on {session.date} logged {outcome.sets_logged} of "
        f"{outcome.sets_prescribed} prescribed working sets",
    )


def session_outcome(
    work: PlannedWork,
    *,
    workouts: Sequence[WeekWorkout] = (),
    trained_unlogged: bool = False,
    cancelled: bool = False,
    spans: Sequence[StatusSpan] = (),
    miss_tagged: bool = False,
) -> SessionOutcome:
    session = work.session
    ordered = in_start_order(workouts)
    trained = (bool(ordered) or trained_unlogged) and not miss_tagged
    on_span = any(span.covers(session.date) for span in spans)
    excluded = cancelled or (on_span and not trained)
    core = session.tier == "core" and not excluded
    coach_led = session.kind == "coach_led"
    in_gate = core and session.kind in GATE_KINDS and (coach_led or work.prescribed_sets > 0)
    lines = lines_against(work.targets, work.held, ordered)
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
        ordered,
        lines,
        cancelled,
        on_span and not trained,
        miss_tagged,
    )


def _passes(work: PlannedWork, pairs: list[tuple[ExposureSet, TargetSet]]) -> bool:
    if len(pairs) < GATE_SET_SHARE * work.prescribed_sets - ROUNDING:
        return False
    prescribed = [t.rpe for sets in work.scheme_targets.values() for t in sets if t.rpe is not None]
    rated = [(s.rpe if s.rpe is not None else t.rpe) for s, t in pairs if t.rpe is not None]
    if not prescribed or not rated:
        return True
    shortfall = sum(prescribed) / len(prescribed) - sum(rated) / len(rated)
    return shortfall <= EFFORT_OFF_RPE + ROUNDING
