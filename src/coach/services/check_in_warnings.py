"""The outside-plan codes `checkin open` raises over a window (docs/spec/week.md, "Which verb
reports which outside-plan code"); `status` reports the same codes while they stand."""

import datetime
from collections.abc import Sequence
from typing import cast

from coach.core.activity_rules import LoggedActivity, activity_cap_exceeded, run_spikes
from coach.core.check_in import Window
from coach.core.closed_week.match import conditioning_activity
from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.ledger_flags import followup_due, niggle_unconstrained, training_max_unused
from coach.core.phase_trend import WeighIns, phase_condition_met, phase_trend_off
from coach.core.planned_week import DAYS_IN_WEEK, week_monday
from coach.services.closed_weeks import WeekLog
from coach.store import decisions, follow_ups, niggles, phases, programs, readings
from coach.store.connection import Connection

WEEK = datetime.timedelta(days=DAYS_IN_WEEK)
# The one v1 scheme that reads a training max (program.md, "Line schemes").
READS_TRAINING_MAX = ("wave_531",)


def check_in_warnings(
    conn: Connection,
    log: WeekLog,
    window: Window,
    *,
    on: datetime.date,
    bodyweight_units: Units,
) -> tuple[Flag, ...]:
    return (
        *_ledger_warnings(conn, on),
        *_phase_warnings(conn, weigh_ins(conn), on, bodyweight_units),
        *_activity_warnings(activities(conn, log), window, on),
        *_training_max_warnings(conn),
    )


def weigh_ins(conn: Connection) -> dict[datetime.date, float]:
    return {
        datetime.date.fromisoformat(str(r["date"])): float(str(r["kg"]))
        for r in readings.live(conn, "weigh_in")
    }


def activities(conn: Connection, log: WeekLog) -> list[LoggedActivity]:
    """Activities, and the Activity view of every conditioning workout: one matched to a
    conditioning session, or an unmatched one classed by its content (week.md, "Match")."""
    found = [
        LoggedActivity(
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
        if workout.kind != "conditioning" and workout.id not in log.conditioning:
            continue
        rated = [s.rpe for e in workout.exposures for s in e.sets if s.rpe is not None]
        view = conditioning_activity(workout.date, workout.minutes, rated)
        found.append(
            LoggedActivity(
                workout.id, view.date, "conditioning", view.minutes, view.rpe, view.quality
            )
        )
    return sorted(found, key=lambda a: (a.date, a.id))


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
    conn: Connection, weigh_ins: WeighIns, on: datetime.date, bodyweight_units: Units
) -> list[Flag]:
    phase = phases.in_force(conn)
    if phase is None:
        return []
    raised = (
        phase_trend_off(phase, weigh_ins, on),
        phase_condition_met(phase, weigh_ins, on, units=bodyweight_units),
    )
    return [flag for flag in raised if flag is not None]


def _activity_warnings(
    activities: Sequence[LoggedActivity], window: Window, on: datetime.date
) -> list[Flag]:
    found: list[Flag] = []
    monday = week_monday(window.start)
    while monday <= window.end:
        flag = activity_cap_exceeded(activities, monday)
        if flag is not None:
            found.append(flag)
        monday += WEEK
    found.extend(run_spikes([a for a in activities if a.date <= on], since=window.start))
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
