"""The check-in card: fifteen fields in a fixed order, each prefilled from the store and asking
only what the store cannot know; a field with nothing to say is dropped (docs/spec/check-in.md,
"Views")."""

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from coach.core.check_in import Window
from coach.core.closed_week.adherence import Adherence
from coach.core.closed_week.dose import trailing_mean
from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import SessionOutcome
from coach.core.closed_week.week import ClosedWeek
from coach.core.fatigue import Proposal
from coach.core.flag import Flag

FIELDS = (
    "header",
    "sessions",
    "week_kind",
    "block",
    "adherence",
    "dose",
    "lifts",
    "readiness",
    "sleep",
    "weight_phase",
    "activities",
    "niggles",
    "follow_ups",
    "notes",
    "deep_tier",
)
FIGURE_PRECISION = 2

type Facts = Mapping[str, object]


@dataclass(frozen=True)
class Ask:
    """A question the card leaves for the athlete, about one record when it names one."""

    kind: str
    about: str | None = None


@dataclass(frozen=True)
class CardField:
    name: str
    facts: Facts
    asks: tuple[Ask, ...] = ()


@dataclass(frozen=True)
class Card:
    window: Window
    tier: str
    fields: tuple[CardField, ...]
    warnings: tuple[Flag, ...] = ()

    @property
    def catch_up(self) -> bool:
        return self.window.catch_up


def assemble(found: Iterable[CardField | None]) -> tuple[CardField, ...]:
    """The fields in card order, the dropped ones left out."""
    by_name = {f.name: f for f in found if f is not None}
    return tuple(by_name[name] for name in FIELDS if name in by_name)


def header(window: Window, tier: str, plan_in_force: str | None) -> CardField:
    return CardField(
        "header",
        {
            "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
            "tier": tier,
            "catch_up": window.catch_up,
            "plan_in_force": plan_in_force,
        },
    )


@dataclass(frozen=True)
class SessionRead:
    """One planned session as the card reads it; `closes` is whether this check-in closes its
    week, which is what makes an untrained session a Miss rather than still to come."""

    outcome: SessionOutcome
    workout: WeekWorkout | None
    closes: bool

    @property
    def ref(self) -> str:
        session = self.outcome.session
        return f"planned_session:{session.date.isoformat()}/{session.session_id}"

    @property
    def state(self) -> str:
        outcome = self.outcome
        if outcome.cancelled:
            return "cancelled"
        if self.workout is not None:
            return "matched"
        if outcome.trained:
            return "trained_unlogged"
        if outcome.rested:
            return "status_span"
        return "missed" if self.closes else "to_come"

    @property
    def session_rpe(self) -> float | None:
        """The mean working-set RPE; a hand-entered workout carries its own."""
        if self.workout is None:
            return None
        rated = [s.rpe for e in self.workout.exposures for s in e.working if s.rpe is not None]
        if rated:
            return round(sum(rated) / len(rated), 1)
        return self.workout.session_rpe


def sessions(reads: Sequence[SessionRead]) -> CardField | None:
    core = [r for r in reads if r.outcome.session.tier == "core"]
    optional = [r for r in reads if r.outcome.session.tier != "core"]
    if not core and not optional:
        return None
    rows: list[Facts] = []
    asks: list[Ask] = []
    for read in core:
        rows.append(_session_row(read))
        if read.state == "missed":
            asks.append(Ask("miss_tag", read.ref))
        if read.state == "matched" and read.session_rpe is None:
            asks.append(Ask("session_rpe", read.ref))
    done = sum(1 for r in optional if r.outcome.trained)
    return CardField(
        "sessions",
        {"core": rows, "optional": {"done": done, "planned": len(optional)}},
        tuple(asks),
    )


def _session_row(read: SessionRead) -> Facts:
    row: dict[str, object] = {
        "session": read.ref,
        "kind": read.outcome.session.kind,
        "state": read.state,
    }
    if read.workout is not None:
        row |= {
            "workout": read.workout.id,
            "minutes": read.workout.minutes,
            "session_rpe": read.session_rpe,
        }
    against = read.outcome.against
    if against is not None:
        row["against"] = {
            "reps_missed": against.reps_missed,
            "effort_off": against.effort_off,
            "rpe_missing": against.rpe_missing,
        }
    return row


def week_kind(closing: Sequence[ClosedWeek]) -> CardField | None:
    if not closing:
        return None
    return CardField("week_kind", {"weeks": [_week_row(w) for w in closing]})


def _week_row(week: ClosedWeek) -> Facts:
    gate = [s for s in week.sessions if s.in_gate]
    return {
        "monday": week.monday.isoformat(),
        "kind": week.kind,
        "trained": f"{sum(1 for s in gate if s.trained)}/{len(gate)}",
        "gate_passed": f"{sum(1 for s in gate if s.passed)}/{len(gate)}",
    }


def block(proposal: Proposal, *, block_id: str | None, standing_from: str | None) -> CardField:
    """`standing_from` names the earlier check-in whose proposal still stands, when this
    window's own triggers propose nothing."""
    facts: dict[str, object] = {
        "block": block_id,
        "hard_weeks": proposal.hard_weeks,
        "ceiling": proposal.ceiling,
        "triggers": [{"trigger": t.name, "evidence": list(t.evidence)} for t in proposal.triggers],
        "proposal": proposal.line,
    }
    if proposal.state == "watch":
        facts["watch"] = proposal.triggers[0].name
    if proposal.shape is not None:
        facts["shape"] = {
            "set_cut_pct": proposal.shape.set_cut_pct,
            "load_cut_pct": proposal.shape.load_cut_pct,
            "rpe_cap": proposal.shape.rpe_cap,
        }
        facts["reasons"] = list(proposal.reasons)
    if standing_from is not None:
        facts["standing_from"] = standing_from
    return CardField("block", facts)


def adherence(found: Adherence) -> CardField:
    figure = None if found.figure is None else round(found.figure, FIGURE_PRECISION)
    return CardField("adherence", {"figure": figure, "weeks": found.weeks, "state": found.state})


def dose(closing: Sequence[ClosedWeek], weeks: Sequence[ClosedWeek]) -> CardField | None:
    """The newest closing week's delivered dose per muscle against the version's target, beside
    the trailing four-ordinary-week mean."""
    if not closing or closing[-1].dose_target is None:
        return None
    latest = closing[-1]
    muscles = sorted(set(latest.dose) | {m for w in weeks for m in w.dose})
    rows = [
        {
            "muscle": muscle,
            "delivered": latest.dose.get(muscle, 0),
            "mean": _rounded(trailing_mean(weeks, muscle)),
        }
        for muscle in muscles
    ]
    return CardField("dose", {"target": latest.dose_target, "muscles": rows})


@dataclass(frozen=True)
class LiftRead:
    """A lift trained in the window: its last top set and its e1RM before and after the window,
    in athlete units."""

    exercise_id: str
    priority: bool
    compound: bool
    top_set: tuple[float | None, int | None, float | None]
    e1rm: float | None = None
    e1rm_before: float | None = None

    @property
    def moved(self) -> bool:
        return self.e1rm != self.e1rm_before


def lifts(reads: Sequence[LiftRead], *, emphasis: str) -> CardField | None:
    """Priority lifts lead and are asked how the top set moved and felt; a `hypertrophy` version
    asks reps and RIR on the lines that moved and a pump and soreness read; `maintenance` asks
    whether the kept lifts held (goals.md, "What the skills ask"). e1RM rows compounds first."""
    if not reads:
        return None
    ordered = sorted(reads, key=lambda r: (not r.priority, not r.compound, r.exercise_id))
    asks = [Ask("top_set_feel", f"exercise:{r.exercise_id}") for r in ordered if r.priority]
    if emphasis == "hypertrophy":
        asks.extend(
            Ask("reps_and_rir", f"exercise:{r.exercise_id}")
            for r in ordered
            if r.moved and not r.priority
        )
        asks.append(Ask("pump_and_soreness"))
    elif emphasis == "maintenance":
        asks.append(Ask("kept_lifts_held"))
    rows = [
        {
            "exercise": r.exercise_id,
            "priority": r.priority,
            "top_set": {"load": r.top_set[0], "reps": r.top_set[1], "rpe": r.top_set[2]},
            "e1rm": r.e1rm,
            "e1rm_before": r.e1rm_before,
        }
        for r in ordered
    ]
    return CardField("lifts", {"emphasis": emphasis, "rows": rows}, tuple(asks))


def readiness(previous: str | None) -> CardField:
    return CardField("readiness", {"previous": previous}, (Ask("readiness"),))


def sleep(nights: Mapping[datetime.date, float], *, short_sleep_week: bool) -> CardField:
    short = sum(1 for hours in nights.values() if hours < 7)
    asks = () if nights else (Ask("sleep_nights"),)
    return CardField(
        "sleep",
        {"nights": len(nights), "short_nights": short, "short_sleep_week": short_sleep_week},
        asks,
    )


@dataclass(frozen=True)
class PhaseRead:
    id: str
    kind: str
    target_rate: float
    observed_rate: float | None
    until: Facts


def weight_phase(
    weigh_ins: int, average: float | None, units: str, phase: PhaseRead | None
) -> CardField:
    facts: dict[str, object] = {
        "weigh_ins": weigh_ins,
        "average_14_days": None if average is None else round(average, 1),
        "units": units,
    }
    if phase is not None:
        facts["phase"] = {
            "id": phase.id,
            "kind": phase.kind,
            "target_rate": phase.target_rate,
            "observed_rate": phase.observed_rate,
            "until": phase.until,
        }
    return CardField("weight_phase", facts, () if weigh_ins else (Ask("weigh_in"),))


@dataclass(frozen=True)
class ActivityRead:
    id: str
    date: datetime.date
    kind: str
    minutes: int | None
    rpe: float
    quality: bool


def activities(
    reads: Sequence[ActivityRead], *, cap: int, spikes: Sequence[str]
) -> CardField | None:
    if not reads:
        return None
    rows = [
        {
            "id": r.id,
            "date": r.date.isoformat(),
            "kind": r.kind,
            "minutes": r.minutes,
            "rpe": r.rpe,
            "quality": r.quality,
        }
        for r in reads
    ]
    quality = sum(1 for r in reads if r.quality)
    return CardField(
        "activities", {"rows": rows, "quality": quality, "cap": cap, "run_spikes": list(spikes)}
    )


@dataclass(frozen=True)
class NiggleRead:
    id: str
    site: str
    status: str
    constraints: int


def niggles(reads: Sequence[NiggleRead]) -> CardField | None:
    if not reads:
        return None
    rows = [
        {"id": r.id, "site": r.site, "status": r.status, "constraints": r.constraints}
        for r in reads
    ]
    return CardField(
        "niggles", {"open": rows}, tuple(Ask("niggle_status", f"niggle:{r.id}") for r in reads)
    )


@dataclass(frozen=True)
class FollowUpRead:
    id: str
    text: str
    due: datetime.date | None

    def due_by(self, day: datetime.date) -> bool:
        return self.due is not None and self.due <= day


def follow_ups(reads: Sequence[FollowUpRead], *, on: datetime.date, deep: bool) -> CardField | None:
    """Those due; a deep check-in lists every open one and asks a disposition each."""
    listed = [r for r in reads if deep or r.due_by(on)]
    if not listed:
        return None
    rows = [
        {"id": r.id, "text": r.text, "due": None if r.due is None else r.due.isoformat()}
        for r in listed
    ]
    return CardField(
        "follow_ups",
        {"listed": rows},
        tuple(Ask("disposition", f"follow_up:{r.id}") for r in listed),
    )


@dataclass(frozen=True)
class NoteRead:
    date: datetime.date
    text: str
    about: str | None = None


def notes(reads: Sequence[NoteRead]) -> CardField | None:
    if not reads:
        return None
    rows = [{"date": r.date.isoformat(), "text": r.text, "about": r.about} for r in reads]
    return CardField("notes", {"notes": rows})


@dataclass(frozen=True)
class DeepRead:
    misses_by_tag: Mapping[str, int] = field(default_factory=dict[str, int])
    observations: tuple[str, ...] = ()


def deep_tier(read: DeepRead, *, tier: str) -> CardField | None:
    if tier != "deep":
        return None
    return CardField(
        "deep_tier",
        {"misses_by_tag": dict(read.misses_by_tag), "observations": list(read.observations)},
        tuple(Ask("confirm_or_retire", f"observation:{o}") for o in read.observations),
    )


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, FIGURE_PRECISION)
