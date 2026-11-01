"""The four fatigue triggers and the light-week proposal (docs/spec/week.md, "Fatigue triggers
and the light-week proposal")."""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from coach.core.check_in import DAY, Window
from coach.core.closed_week.sessions import TargetSet
from coach.core.cut import LightShape, light_shape
from coach.core.exposure import ExposureSet
from coach.core.program.form import Deload

type ProposalState = Literal["propose", "watch", "none", "skipped"]

# rn:sleep-dieting.1: 7 hours a night; 4 of 7 nights and the 4-night floor are opinion.
SHORT_NIGHT_HOURS = 7
SHORT_NIGHTS = 4
MEASURED_NIGHTS = 4
NIGHTS_READ = 7
# rn:deloads.5: two triggers propose, one is a watch.
PROPOSE_AT = 2
# rn:deloads.4: below 3 completed hard weeks nothing is proposed.
MIN_HARD_WEEKS = 3
# rn:deloads.9: the standard deload takes 10 % off loads; rn:deloads.10 holds them for
# readiness or sleep alone.
LOAD_CUT_PCT = 10
LOAD_CUT_REASONS = ("ceiling", "rpe_drift", "niggle")
# rn:autoregulation.4: 1 RPE or more over target on 2 or more working sets.
DRIFT_RPE = 1
DRIFT_SETS = 2
# Load is compared in athlete units to two decimals.
LOAD_TOLERANCE = 0.005


@dataclass(frozen=True)
class Trigger:
    """`evidence` holds refs, or the nights' dates for sleep, which has no ref kind."""

    name: str
    evidence: tuple[str, ...] = ()


def short_sleep_week(
    nights: Mapping[datetime.date, float], check_in: datetime.date
) -> Trigger | None:
    """The 7 calendar nights ending the night before the check-in."""
    read = [check_in - DAY * n for n in range(1, NIGHTS_READ + 1)]
    measured = {night: nights[night] for night in read if night in nights}
    short = sorted(night for night, hours in measured.items() if hours < SHORT_NIGHT_HOURS)
    if len(measured) < MEASURED_NIGHTS or len(short) < SHORT_NIGHTS:
        return None
    return Trigger("short_sleep_week", tuple(night.isoformat() for night in short))


@dataclass(frozen=True)
class DriftExposure:
    """One exposure of a compound lift at its prescription, outside deload, light and return
    work: each logged working set beside its own prescribed set, and whether more working sets
    were logged than prescribed."""

    exercise_id: str
    date: datetime.date
    ref: str
    sets: tuple[tuple[ExposureSet, TargetSet], ...]
    extra: bool = False

    @property
    def judged(self) -> bool:
        return not self.extra and not any(_beyond(s, t) for s, t in self.sets)

    @property
    def drifted(self) -> bool:
        over = sum(
            1
            for s, t in self.sets
            if s.rpe is not None and t.rpe is not None and s.rpe - t.rpe >= DRIFT_RPE
        )
        return self.judged and over >= DRIFT_SETS

    @property
    def steady(self) -> bool:
        return self.judged and not self.drifted


@dataclass(frozen=True)
class NiggleHistory:
    """A niggle's dated status events, oldest first."""

    id: str
    events: tuple[tuple[datetime.date, str], ...]


@dataclass(frozen=True)
class Proposal:
    """`reasons` names the triggers that fired and `ceiling` when the count reached it; `shape`
    is the light week proposed, set only when `state` is `propose`."""

    state: ProposalState
    triggers: tuple[Trigger, ...]
    hard_weeks: int
    ceiling: int | None = None
    shape: LightShape | None = None

    @property
    def reasons(self) -> tuple[str, ...]:
        names = tuple(t.name for t in self.triggers)
        return (*names, "ceiling") if self.at_ceiling else names

    @property
    def at_ceiling(self) -> bool:
        return self.ceiling is not None and self.hard_weeks >= self.ceiling

    @property
    def line(self) -> str:
        """The Block line's proposal as the card states it."""
        if self.state == "skipped":
            return f"skipped ({self.hard_weeks} hard weeks)"
        return "light_week" if self.state == "propose" else "none"


def readiness_trigger(readiness: str | None) -> Trigger | None:
    return Trigger("readiness") if readiness == "poor" else None


def niggle_trigger(niggles: Iterable[NiggleHistory], window: Window) -> Trigger | None:
    fired = tuple(f"niggle:{n.id}" for n in niggles if _aggravated_in(n, window))
    return Trigger("niggle", fired) if fired else None


def rpe_drift(exposures: Iterable[DriftExposure], window: Window) -> Trigger | None:
    """Two consecutive drifting exposures of one lift, the later inside the window, after an
    earlier steady one; two with no steady one before read as load calibration."""
    by_lift: dict[str, list[DriftExposure]] = {}
    for exposure in sorted(exposures, key=lambda e: e.date):
        by_lift.setdefault(exposure.exercise_id, []).append(exposure)
    fired: list[str] = []
    for run in by_lift.values():
        for i in range(2, len(run)):
            first, second = run[i - 1], run[i]
            if (
                first.drifted
                and second.drifted
                and window.start <= second.date <= window.end
                and any(e.steady for e in run[: i - 1])
            ):
                fired.extend((first.ref, second.ref))
                break
    return Trigger("rpe_drift", tuple(fired)) if fired else None


def propose(triggers: Sequence[Trigger], *, hard_weeks: int, deload: Deload | None) -> Proposal:
    ceiling = deload.hard_weeks_ceiling if deload else None
    proposal = Proposal("none", tuple(triggers), hard_weeks, ceiling)
    if proposal.at_ceiling:
        state: ProposalState = "propose"
    elif hard_weeks < MIN_HARD_WEEKS:
        state = "skipped"
    elif len(triggers) >= PROPOSE_AT:
        state = "propose"
    else:
        state = "watch" if triggers else "none"
    if state != "propose":
        return Proposal(state, tuple(triggers), hard_weeks, ceiling)
    return Proposal(state, tuple(triggers), hard_weeks, ceiling, _shape(proposal, deload))


def _shape(proposal: Proposal, deload: Deload | None) -> LightShape:
    policy = light_shape(deload, {})
    if not set(proposal.reasons) & set(LOAD_CUT_REASONS):
        return policy
    return LightShape(policy.set_cut_pct, max(policy.load_cut_pct, LOAD_CUT_PCT), policy.rpe_cap)


def _aggravated_in(niggle: NiggleHistory, window: Window) -> bool:
    before = [status for day, status in niggle.events if day < window.start]
    if before and before[-1] == "aggravated":
        return True
    return any(
        status == "aggravated" and window.start <= day <= window.end
        for day, status in niggle.events
    )


def _beyond(logged: ExposureSet, target: TargetSet) -> bool:
    """Heavier, or longer (more reps) than the set prescribed."""
    heavier = (
        logged.load is not None
        and target.load is not None
        and logged.load.amount > target.load + LOAD_TOLERANCE
    )
    longer = logged.reps is not None and target.top is not None and logged.reps > target.top
    return heavier or longer
