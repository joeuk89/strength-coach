"""`coach progress`: where the athlete stands against the Goal at the block boundary
(docs/spec/goals.md, "`coach progress`")."""

import datetime
from collections import Counter
from collections.abc import Mapping, Sequence

from coach.core.cadence import BlockSpan
from coach.core.closed_week.week import ClosedWeek
from coach.core.config import Units
from coach.core.e1rm import e1rm
from coach.core.exposure import Exposure
from coach.core.line_history import newest_first, ordinary, since_redesign
from coach.core.linear import resets
from coach.core.phase_trend import observed_rate, phase_condition_met
from coach.core.prescription import DecisionInForce
from coach.core.program.form import Line, ProgramForm
from coach.core.progress import (
    PRECISION,
    AdherenceRead,
    DoseWeek,
    GoalRead,
    LiftProgress,
    LineHistory,
    PhaseRead,
    Progress,
    best_set,
    milestone_read,
)
from coach.core.stall import judged, stall_streak
from coach.services.cadence import cadence_signals, closed_spans
from coach.services.closed_weeks import ClosedWeeks, closed_weeks
from coach.services.history import read_history
from coach.services.ladders import ladder_reads, rung_decisions, standing_line
from coach.store import annotations, check_ins, goals, phases, programs, readings
from coach.store.connection import Connection

BLOCKS_READ = 3
_DAY = datetime.timedelta(days=1)


def progress(
    conn: Connection,
    *,
    on: datetime.date,
    units: Units,
    bodyweight_units: Units,
    zone: datetime.tzinfo,
    full: bool = False,
) -> Progress:
    closed = closed_weeks(conn, units)
    spans = closed_spans(closed)
    block = spans[-1] if spans else None
    dosed = _weeks_in(closed, block)
    exposures = read_history(conn, units).lifting
    versions = programs.newest_first(conn)
    form = versions[0].form if versions else None
    stored = _goal(conn)
    priority = stored.goal.priority_lifts if stored else ()
    signals = cadence_signals(conn, closed, units=units, on=on, zone=zone)
    by_exercise = {str(s.scope.exercise_id): s.code for s in signals}
    rungs = rung_decisions(conn, zone, on)
    opened = programs.block_opened(conn)
    redesigned = None if opened is None else datetime.date.fromisoformat(opened)
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
                redesigned,
                on,
                by_exercise.get(exercise),
                rungs,
            )
            for exercise in priority
        ),
        milestones=tuple(
            milestone_read(m, exposures, weigh_ins, units)
            for m in (stored.goal.milestones if stored else ())
        ),
        ladders=ladder_reads(conn, units=units, on=on, zone=zone),
        dose=_dose(dosed),
        dose_target=_dose_target(dosed),
        adherence=_adherence(conn, closed, block),
        phase=_phase(conn, weigh_ins, on, bodyweight_units),
        goal=GoalRead(stored.goal.kind, stored.adopted, stored.goal.why) if stored else None,
        history=_history(form, exposures, block) if full and form else (),
        signals=signals,
    )


def newest_day(conn: Connection, units: Units) -> datetime.date | None:
    """The newest day the store records a logged exposure, a live weigh-in, a current
    Check-in's window end or the open Phase's start."""
    phase = phases.in_force(conn)
    days = [
        *(e.date for e in read_history(conn, units).exposures),
        *(datetime.date.fromisoformat(str(r["date"])) for r in readings.live(conn, "weigh_in")),
        *(end for _, end in check_ins.current_windows(conn)),
        *((phase.opened,) if phase else ()),
    ]
    return max(days, default=None)


def _goal(conn: Connection) -> goals.StoredGoal | None:
    goal_id = goals.current_id(conn)
    return goals.get(conn, goal_id) if goal_id else None


def _lift(
    exercise: str,
    form: ProgramForm | None,
    exposures: Sequence[Exposure],
    spans: Sequence[BlockSpan],
    since: datetime.date | None,
    redesigned: datetime.date | None,
    today: datetime.date,
    signal: str | None,
    rungs: Sequence[DecisionInForce],
) -> LiftProgress:
    line = _line(form, exercise)
    judged_line = _judged_line(form, exercise)
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
        stall_streak=_stall_streak(judged_line, since_redesign(history, redesigned), rungs),
        resets=_resets(judged_line, history),
        signal=signal,
    )


def _judged_line(form: ProgramForm | None, exercise: str) -> tuple[str, Line] | None:
    """The exercise's first line in a judged session, with that session's id."""
    return next(
        (
            (session.id, line)
            for session in (form.sessions if form else ())
            if judged(session.kind)
            for line in session.lines
            if line.exercise == exercise
        ),
        None,
    )


def _of_session(history: Sequence[Exposure], session_id: str) -> tuple[Exposure, ...]:
    """What the line in `session_id` reads: exposures matched to it or to no session."""
    return tuple(e for e in history if e.session_id in (None, session_id))


def _stall_streak(
    judged_line: tuple[str, Line] | None,
    history: Sequence[Exposure],
    rungs: Sequence[DecisionInForce],
) -> int:
    """Read on the judged line, a ladder's standing rung from its start; 0 when it has none."""
    if judged_line is None:
        return 0
    session_id, line = judged_line
    read = _of_session(history, session_id)
    return len(stall_streak(*standing_line(line, session_id, rungs, read)))


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
        since = version.adopted_on
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


def _resets(judged_line: tuple[str, Line] | None, history: Sequence[Exposure]) -> int:
    if judged_line is None or judged_line[1].scheme.name != "linear":
        return 0
    session_id, line = judged_line
    read = _of_session(history, session_id)
    loads = [e.top_load for e in read if e.top_load is not None]
    return len(resets(line, read, None, loads[0].mode)) if loads else 0


def _weeks_in(closed: ClosedWeeks, block: BlockSpan | None) -> list[ClosedWeek]:
    if block is None:
        return []
    return [w for w in closed.weeks if block.holds(w.monday)]


def _dose(weeks: Sequence[ClosedWeek]) -> tuple[DoseWeek, ...]:
    return tuple(
        DoseWeek(
            week.monday,
            week.kind,
            {m: round(v, 1) for m, v in sorted(week.dose.items())},
            dict(week.lift_dose),
        )
        for week in weeks
    )


def _dose_target(weeks: Sequence[ClosedWeek]) -> dict[str, int]:
    """The targets the block's newest closed week was judged against."""
    if not weeks or weeks[-1].dose_target is None:
        return {}
    return {"per_muscle": weeks[-1].dose_target, **weeks[-1].lift_dose_target}


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
