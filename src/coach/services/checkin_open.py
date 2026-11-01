"""`checkin open`: the check-in card at a date and the outside-plan codes it reports (docs/spec/
check-in.md, "Views"; docs/spec/week.md, "Which verb reports which outside-plan code")."""

import datetime
from collections import Counter
from collections.abc import Sequence
from typing import cast

from coach.core import check_in_card as card
from coach.core.activity_rules import (
    QUALITY_CAP,
    Bout,
    activity_cap_exceeded,
    run_spikes,
)
from coach.core.check_in import Window, check_in_window
from coach.core.check_in_card import Card, CardField
from coach.core.clock import Clock
from coach.core.closed_week.adherence import adherence
from coach.core.closed_week.match import conditioning_activity
from coach.core.closed_week.week import ClosedWeek
from coach.core.config import DEFAULT_CHECKIN_CADENCE_DAYS, Units
from coach.core.e1rm import e1rm
from coach.core.exposure import Exposure
from coach.core.flag import Flag
from coach.core.ledger_flags import followup_due, niggle_unconstrained, training_max_unused
from coach.core.phase_trend import (
    WeighIns,
    fourteen_day_average,
    observed_rate,
    phase_condition_met,
    phase_trend_off,
)
from coach.core.planned_week import DAYS_IN_WEEK, week_monday
from coach.core.units import from_kg
from coach.services.closed_weeks import WeekLog
from coach.services.fatigue import COMPOUND_PATTERNS, Fatigue
from coach.services.status import check_in_due_on
from coach.store import (
    annotations,
    check_ins,
    decisions,
    exercises,
    follow_ups,
    goals,
    niggles,
    notes,
    observations,
    phases,
    programs,
    readings,
    week_plans,
)
from coach.store.connection import Connection
from coach.store.rows import Row

WEEK = datetime.timedelta(days=DAYS_IN_WEEK)
_DAY = datetime.timedelta(days=1)
# The one v1 scheme that reads a training max (program.md, "Line schemes").
READS_TRAINING_MAX = ("wave_531",)


def checkin_open(
    conn: Connection,
    clock: Clock,
    *,
    units: Units,
    date: datetime.date | None = None,
    tier: str | None = None,
    cadence_days: int = DEFAULT_CHECKIN_CADENCE_DAYS,
) -> Card:
    """`tier` only raises the derived tier to `deep`, and is honoured on a catch-up."""
    on = date or clock.today()
    previous = check_ins.newest_current(conn, before=on)
    window = check_in_window(
        on,
        previous_end=previous.window.end if previous else None,
        first_plan_monday=week_plans.first_week(conn),
    )
    log = WeekLog(conn, units)
    fatigue = Fatigue(conn, log)
    earlier = [r for r in fatigue.check_ins if r.date < on]
    windows = [*((r.window.start, r.window.end) for r in earlier), (window.start, window.end)]
    opened = fatigue.opened(window, previous.readiness if previous else None, windows)
    standing = fatigue.standing(before=on)
    proposed = standing is not None or opened.proposal.state == "propose"
    due = check_in_due_on(conn, on, cadence_days, light_week_proposed=proposed)
    derived = "light" if window.catch_up else due.tier
    chosen = "deep" if tier == "deep" else derived
    closed = log.closed_by(windows)
    closing = [w for w in closed.weeks if window.start <= w.monday + WEEK - _DAY <= window.end]
    plan = week_plans.in_force(conn, week_monday(on).isoformat())
    version = programs.latest(conn)
    weigh_ins = _weigh_ins(conn)
    bouts = _bouts(conn, log)
    phase = phases.in_force(conn)
    fields: list[CardField | None] = [
        card.header(window, chosen, None if plan is None else str(plan["id"])),
        card.sessions(_session_reads(log, window, closing)),
        card.week_kind(closing),
        None
        if version is None
        else card.block(
            opened.proposal,
            block_id=opened.block.id if opened.block else None,
            standing=standing.proposal if standing else None,
            standing_from=standing.check_in if standing else None,
        ),
        None if version is None else card.adherence(adherence(closed.weeks, on)),
        card.dose(closing, closed.weeks),
        card.lifts(
            _lift_reads(conn, log, window),
            emphasis=version.form.emphasis if version else "hypertrophy",
        ),
        card.readiness(previous.readiness if previous else None),
        card.sleep(
            {d: h for d, h in fatigue.nights.items() if window.start <= d <= window.end},
            short_sleep_week=any(t.name == "short_sleep_week" for t in opened.proposal.triggers),
        ),
        card.weight_phase(
            sum(1 for d in weigh_ins if window.start <= d <= window.end),
            _in_units(fourteen_day_average(weigh_ins, on), units),
            units,
            None
            if phase is None
            else card.PhaseRead(
                phase.id,
                phase.kind,
                phase.rate_pct_bw_per_week,
                observed_rate(weigh_ins, on),
                {"kind": phase.until.kind, "value": _plain(phase.until.value)},
            ),
        ),
        card.activities(
            [
                card.ActivityRead(b.id, b.date, b.kind, b.minutes, b.rpe, b.quality)
                for b in bouts
                if window.start <= b.date <= window.end
            ],
            cap=QUALITY_CAP,
            spikes=[
                str(f.scope.workout_id)
                for f in run_spikes([b for b in bouts if b.date <= on], since=window.start)
            ],
        ),
        card.niggles(_niggle_reads(conn)),
        card.follow_ups(_follow_up_reads(conn), on=on, deep=chosen == "deep"),
        card.notes(_note_reads(conn, window)),
        card.deep_tier(_deep_read(conn), tier=chosen),
    ]
    warnings = (
        *_ledger_warnings(conn, on),
        *_phase_warnings(conn, weigh_ins, on, units),
        *_activity_warnings(bouts, window, on),
        *_training_max_warnings(conn),
    )
    return Card(window, chosen, card.assemble(fields), warnings)


def _session_reads(
    log: WeekLog, window: Window, closing: Sequence[ClosedWeek]
) -> list[card.SessionRead]:
    closes = {w.monday for w in closing}
    found: list[card.SessionRead] = []
    if not log.redesigns:
        return found
    monday = max(week_monday(window.start), week_monday(log.redesigns[0]))
    while monday <= window.end:
        for outcome in log.week(monday).sessions:
            if not window.start <= outcome.session.date <= window.end:
                continue
            workout = None if outcome.workout_id is None else log.workout(outcome.workout_id)
            found.append(card.SessionRead(outcome, workout, monday in closes))
        monday += WEEK
    return found


def _lift_reads(conn: Connection, log: WeekLog, window: Window) -> list[card.LiftRead]:
    every = [e for w in log.workouts for e in w.exposures]
    inside = [e for e in every if window.start <= e.date <= window.end and e.working]
    patterns = {str(r["id"]): r["pattern"] for r in exercises.every(conn)}
    priority = _priority_lifts(conn)
    latest: dict[str, Exposure] = {}
    for exposure in sorted(inside, key=lambda e: e.date):
        latest[exposure.exercise_id] = exposure
    reads: list[card.LiftRead] = []
    for exercise_id, exposure in latest.items():
        top = max(exposure.working, key=lambda s: (s.load.amount if s.load else 0, s.reps or 0))
        after = e1rm(every, exercise_id, window.end + _DAY)
        before = e1rm(every, exercise_id, window.start)
        reads.append(
            card.LiftRead(
                exercise_id,
                exercise_id in priority,
                patterns.get(exercise_id) in COMPOUND_PATTERNS,
                (top.load.amount if top.load else None, top.reps, top.rpe),
                after.load.amount if after else None,
                before.load.amount if before else None,
            )
        )
    return reads


def _niggle_reads(conn: Connection) -> list[card.NiggleRead]:
    return [
        card.NiggleRead(
            str(n["id"]),
            str(n["site"]),
            str(n["status"]),
            len(cast(list[Row], n["constraints"])),
        )
        for n in niggles.every(conn)
        if n["status"] != "resolved"
    ]


def _follow_up_reads(conn: Connection) -> list[card.FollowUpRead]:
    return [
        card.FollowUpRead(
            str(f["id"]),
            str(f["text"]),
            None if f["due"] is None else datetime.date.fromisoformat(str(f["due"])),
        )
        for f in follow_ups.every(conn)
        if f["kind"] in ("kept", "deferred")
    ]


def _note_reads(conn: Connection, window: Window) -> list[card.NoteRead]:
    found: list[card.NoteRead] = []
    for row in notes.every(conn):
        day = datetime.date.fromisoformat(str(row["date"]))
        if window.start <= day <= window.end:
            found.append(card.NoteRead(day, str(row["text"]), cast(str | None, row["about"])))
    return found


def _deep_read(conn: Connection) -> card.DeepRead:
    """Misses by tag since the last deep check-in, and the open Observations."""
    since = check_ins.last_deep(conn)
    tags: Counter[str] = Counter()
    for row in annotations.every(conn):
        if row["kind"] != "miss_tag" or row["withdrawn_by"] or row["withdraws"]:
            continue
        day = str(row["target"]).partition(":")[2][:10]
        if since is None or day > since.isoformat():
            tags[str(row["because"])] += 1
    return card.DeepRead(dict(sorted(tags.items())), tuple(observations.current(conn)))


def _ledger_warnings(conn: Connection, on: datetime.date) -> list[Flag]:
    found = [
        followup_due(str(f["id"]), str(f["due"]))
        for f in follow_ups.every(conn)
        if f["kind"] in ("kept", "deferred") and f["due"] and str(f["due"]) <= on.isoformat()
    ]
    found.extend(
        niggle_unconstrained(str(n["id"]), str(n["opened"]))
        for n in niggles.every(conn)
        if n["status"] != "resolved" and not n["constraints"]
    )
    return found


def _phase_warnings(
    conn: Connection, weigh_ins: WeighIns, on: datetime.date, units: Units
) -> list[Flag]:
    phase = phases.in_force(conn)
    if phase is None:
        return []
    raised = (
        phase_trend_off(phase, weigh_ins, on),
        phase_condition_met(phase, weigh_ins, on, units=units),
    )
    return [flag for flag in raised if flag is not None]


def _activity_warnings(bouts: Sequence[Bout], window: Window, on: datetime.date) -> list[Flag]:
    found: list[Flag] = []
    monday = week_monday(window.start)
    while monday <= window.end:
        flag = activity_cap_exceeded(bouts, monday)
        if flag is not None:
            found.append(flag)
        monday += WEEK
    found.extend(run_spikes([b for b in bouts if b.date <= on], since=window.start))
    return found


def _training_max_warnings(conn: Connection) -> list[Flag]:
    version = programs.latest(conn)
    schemes: dict[str, list[str]] = {}
    if version is not None:
        for session in version.form.sessions:
            for line in session.lines:
                schemes.setdefault(line.exercise, []).append(line.scheme.name)
    found: list[Flag] = []
    for row in decisions.in_force(conn):
        if row["kind"] != "training_max":
            continue
        exercise_id = str(row["exercise_id"])
        read_by = schemes.get(exercise_id, [])
        if not any(s in READS_TRAINING_MAX for s in read_by):
            scheme = read_by[0] if read_by else None
            found.append(training_max_unused(exercise_id, scheme, str(row["id"])))
    return found


def _weigh_ins(conn: Connection) -> dict[datetime.date, float]:
    return {
        datetime.date.fromisoformat(str(r["date"])): float(str(r["kg"]))
        for r in readings.live(conn, "weigh_in")
    }


def _bouts(conn: Connection, log: WeekLog) -> list[Bout]:
    """Activities, and the Activity view of every conditioning workout (week.md, "What an
    unmatched workout is")."""
    found = [
        Bout(
            str(r["id"]),
            datetime.date.fromisoformat(str(r["date"])),
            str(r["kind"]),
            cast(int | None, r["minutes"]),
            float(str(r["rpe"])),
            bool(r["quality"]),
            cast(float | None, r["distance_km"]),
        )
        for r in readings.live(conn, "activity")
    ]
    for workout in log.workouts:
        if workout.kind != "conditioning":
            continue
        rated = [s.rpe for e in workout.exposures for s in e.sets if s.rpe is not None]
        view = conditioning_activity(workout.date, workout.minutes, rated)
        found.append(
            Bout(workout.id, view.date, "conditioning", view.minutes, view.rpe, view.quality)
        )
    return sorted(found, key=lambda b: (b.date, b.id))


def _priority_lifts(conn: Connection) -> tuple[str, ...]:
    goal_id = goals.current_id(conn)
    stored = goals.get(conn, goal_id) if goal_id else None
    return stored.goal.priority_lifts if stored else ()


def _in_units(kg: float | None, units: Units) -> float | None:
    return None if kg is None else from_kg(kg, units)


def _plain(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime.date) else value
