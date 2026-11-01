"""`coach progress`: where the athlete stands against the Goal at the block boundary
(docs/spec/goals.md, "`coach progress`")."""

import datetime
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from coach.core.cadence import BlockSpan
from coach.core.clock import Clock
from coach.core.closed_week.dose import is_hard
from coach.core.closed_week.week import ClosedWeek
from coach.core.config import Units
from coach.core.e1rm import e1rm
from coach.core.exposure import Exposure
from coach.core.flag import Flag
from coach.core.line_history import newest_first, ordinary
from coach.core.linear import resets
from coach.core.phase_trend import observed_rate, phase_condition_met
from coach.core.planned_week import DAYS_IN_WEEK
from coach.core.program.form import Line, ProgramForm
from coach.core.progress import PRECISION, BestSet, MilestoneRead, best_set, milestone_read
from coach.core.stall import stall_streak
from coach.services.cadence import cadence_signals, closed_spans
from coach.services.closed_weeks import ClosedWeeks, closed_weeks
from coach.services.history import read_history
from coach.store import annotations, goals, phases, programs, readings
from coach.store.connection import Connection

BLOCKS_READ = 3
_DAY = datetime.timedelta(days=1)


@dataclass(frozen=True)
class LiftProgress:
    """`e1rm_by_block` is the e1RM at the end of each of the last three closed Blocks, oldest
    first; the changes run over the closed Block and over those three."""

    exercise_id: str
    scheme: str | None
    e1rm_now: float | None
    e1rm_by_block: tuple[tuple[str, float | None], ...]
    change_over_block: float | None
    change_over_three: float | None
    best: BestSet | None
    stall_streak: int
    resets: int
    signal: str | None


@dataclass(frozen=True)
class DoseWeek:
    """Hard sets delivered: fractional per muscle, whole per priority lift."""

    monday: datetime.date
    kind: str
    muscles: Mapping[str, float]
    lifts: Mapping[str, int]


@dataclass(frozen=True)
class AdherenceRead:
    """Core sessions over the closed Block's ordinary weeks, optional sessions trained, and the
    misses by tag inside it."""

    core_planned: int
    core_trained: int
    optional_trained: int
    misses: Mapping[str, int]


@dataclass(frozen=True)
class PhaseRead:
    kind: str
    target_rate: float
    observed_rate: float | None
    until: Mapping[str, object]
    met: bool


@dataclass(frozen=True)
class GoalRead:
    kind: str
    adopted: str
    why: str


@dataclass(frozen=True)
class LineHistory:
    exercise_id: str
    session_id: str
    exposures: tuple[tuple[datetime.date, tuple[tuple[float | None, int | None], ...]], ...]


@dataclass(frozen=True)
class Progress:
    block: BlockSpan | None
    lifts: tuple[LiftProgress, ...] = ()
    milestones: tuple[MilestoneRead, ...] = ()
    dose: tuple[DoseWeek, ...] = ()
    dose_target: Mapping[str, int] = field(default_factory=dict[str, int])
    adherence: AdherenceRead | None = None
    phase: PhaseRead | None = None
    goal: GoalRead | None = None
    history: tuple[LineHistory, ...] = ()
    signals: tuple[Flag, ...] = ()


def progress(
    conn: Connection,
    clock: Clock,
    *,
    units: Units,
    bodyweight_units: Units,
    full: bool = False,
) -> Progress:
    today = clock.today()
    closed = closed_weeks(conn, units)
    spans = closed_spans(closed)
    block = spans[-1] if spans else None
    exposures = read_history(conn, units).exposures
    versions = programs.newest_first(conn)
    form = versions[0].form if versions else None
    stored = _goal(conn)
    priority = stored.goal.priority_lifts if stored else ()
    signals = cadence_signals(conn, closed, units=units, on=today)
    by_exercise = {str(s.scope.exercise_id): s.code for s in signals}
    weigh_ins = {
        datetime.date.fromisoformat(str(r["date"])): float(str(r["kg"]))
        for r in readings.live(conn, "weigh_in")
    }
    return Progress(
        block=block,
        lifts=tuple(
            _lift(
                exercise,
                form,
                exposures,
                spans,
                _scheme_since(versions, exercise),
                today,
                by_exercise.get(exercise),
            )
            for exercise in priority
        ),
        milestones=tuple(
            milestone_read(m, exposures, weigh_ins, units)
            for m in (stored.goal.milestones if stored else ())
        ),
        dose=_dose(closed, block, exposures, priority),
        dose_target=_dose_target(form, priority),
        adherence=_adherence(conn, closed, block),
        phase=_phase(conn, weigh_ins, today, bodyweight_units),
        goal=GoalRead(stored.goal.kind, stored.adopted, stored.goal.why) if stored else None,
        history=_history(form, exposures, block) if full and form else (),
        signals=signals,
    )


def _goal(conn: Connection) -> goals.StoredGoal | None:
    goal_id = goals.current_id(conn)
    return goals.get(conn, goal_id) if goal_id else None


def _lift(
    exercise: str,
    form: ProgramForm | None,
    exposures: Sequence[Exposure],
    spans: Sequence[BlockSpan],
    since: datetime.date | None,
    today: datetime.date,
    signal: str | None,
) -> LiftProgress:
    line = _line(form, exercise)
    read = spans[-BLOCKS_READ:]
    at_end = tuple((s.id, _e1rm(exposures, exercise, s.end + _DAY)) for s in read)
    history = ordinary(
        newest_first(
            e
            for e in exposures
            if e.exercise_id == exercise and (since is None or since <= e.date) and e.date <= today
        )
    )
    return LiftProgress(
        exercise_id=exercise,
        scheme=line.scheme.name if line else None,
        e1rm_now=_e1rm(exposures, exercise, today + _DAY),
        e1rm_by_block=at_end,
        change_over_block=_change(exposures, exercise, read[-1:]),
        change_over_three=_change(exposures, exercise, read),
        best=best_set(exposures, exercise),
        stall_streak=len(stall_streak(line, history)) if line else 0,
        resets=_resets(line, history),
        signal=signal,
    )


def _scheme_since(versions: Sequence[programs.VersionRow], exercise: str) -> datetime.date | None:
    """The adoption date of the oldest version in the unbroken run giving the exercise its
    current scheme."""
    current = _line(versions[0].form, exercise) if versions else None
    if current is None:
        return None
    since: datetime.date | None = None
    for version in versions:
        line = _line(version.form, exercise)
        if line is None or line.scheme.name != current.scheme.name:
            break
        since = datetime.date.fromisoformat(version.adopted[:10])
    return since


def _line(form: ProgramForm | None, exercise: str) -> Line | None:
    return None if form is None else form.first_line(exercise)


def _e1rm(exposures: Sequence[Exposure], exercise: str, on: datetime.date) -> float | None:
    found = e1rm(exposures, exercise, on)
    return None if found is None else found.load.amount


def _change(
    exposures: Sequence[Exposure], exercise: str, spans: Sequence[BlockSpan]
) -> float | None:
    if not spans:
        return None
    start = _e1rm(exposures, exercise, spans[0].start)
    end = _e1rm(exposures, exercise, spans[-1].end + _DAY)
    return None if start is None or end is None else round(end - start, PRECISION)


def _resets(line: Line | None, history: Sequence[Exposure]) -> int:
    if line is None or line.scheme.name != "linear":
        return 0
    loads = [e.top_load for e in history if e.top_load is not None]
    return len(resets(line, history, None, loads[0].mode)) if loads else 0


def _weeks_in(closed: ClosedWeeks, block: BlockSpan | None) -> list[ClosedWeek]:
    if block is None:
        return []
    return [w for w in closed.weeks if block.holds(w.monday)]


def _dose(
    closed: ClosedWeeks,
    block: BlockSpan | None,
    exposures: Sequence[Exposure],
    priority: Sequence[str],
) -> tuple[DoseWeek, ...]:
    found: list[DoseWeek] = []
    for week in _weeks_in(closed, block):
        sunday = week.monday + datetime.timedelta(days=DAYS_IN_WEEK - 1)
        lifts = {
            exercise: sum(
                1
                for e in exposures
                if e.exercise_id == exercise and week.monday <= e.date <= sunday
                for s in e.working
                if is_hard(s.rpe)
            )
            for exercise in priority
        }
        muscles = {m: round(v, 1) for m, v in sorted(week.dose.items())}
        found.append(DoseWeek(week.monday, week.kind, muscles, lifts))
    return tuple(found)


def _dose_target(form: ProgramForm | None, priority: Sequence[str]) -> dict[str, int]:
    if form is None or form.dose is None:
        return {}
    lifts = {lift: form.dose.lift[lift] for lift in priority if lift in form.dose.lift}
    return {"per_muscle": form.dose.per_muscle, **lifts}


def _adherence(
    conn: Connection, closed: ClosedWeeks, block: BlockSpan | None
) -> AdherenceRead | None:
    if block is None:
        return None
    weeks = _weeks_in(closed, block)
    ordinary_weeks = [w for w in weeks if w.ordinary]
    optional = sum(
        1
        for w in weeks
        for outcome in w.sessions
        if outcome.session.tier == "optional" and outcome.trained
    )
    return AdherenceRead(
        sum(w.adherence_planned for w in ordinary_weeks),
        sum(w.adherence_trained for w in ordinary_weeks),
        optional,
        _misses(conn, block),
    )


def _misses(conn: Connection, block: BlockSpan) -> dict[str, int]:
    tags: Counter[str] = Counter()
    for row in annotations.every(conn):
        if row["kind"] != "miss_tag" or row["withdrawn_by"] or row["withdraws"]:
            continue
        day = datetime.date.fromisoformat(str(row["target"]).partition(":")[2][:10])
        if block.holds(day):
            tags[str(row["because"])] += 1
    return dict(sorted(tags.items()))


def _phase(
    conn: Connection,
    weigh_ins: Mapping[datetime.date, float],
    today: datetime.date,
    bodyweight_units: Units,
) -> PhaseRead | None:
    phase = phases.in_force(conn)
    if phase is None:
        return None
    value = phase.until.value
    return PhaseRead(
        phase.kind,
        phase.rate_pct_bw_per_week,
        observed_rate(weigh_ins, today),
        {
            "kind": phase.until.kind,
            "value": value.isoformat() if isinstance(value, datetime.date) else value,
        },
        phase_condition_met(phase, weigh_ins, today, units=bodyweight_units) is not None,
    )


def _history(
    form: ProgramForm, exposures: Sequence[Exposure], block: BlockSpan | None
) -> tuple[LineHistory, ...]:
    since = block.start if block else datetime.date.min
    found: list[LineHistory] = []
    for session in form.sessions:
        for line in session.lines:
            logged = sorted(
                (e for e in exposures if e.exercise_id == line.exercise and e.date >= since),
                key=lambda e: e.date,
            )
            found.append(
                LineHistory(
                    line.exercise,
                    session.id,
                    tuple(
                        (
                            e.date,
                            tuple(
                                (None if s.load is None else s.load.amount, s.reps)
                                for s in e.working
                            ),
                        )
                        for e in logged
                    ),
                )
            )
    return tuple(found)
