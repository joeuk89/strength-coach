"""Where each `exercise_ladder` line of the version in force stands (ADR 0023): what the check-in
card, the progress view and the pages read, from the same rule `plan draft` prescribes by."""

import datetime
from collections.abc import Mapping, Sequence
from typing import cast

from coach.core.config import Units
from coach.core.exercise_ladder import LadderRead, ladder_read, standing_rung
from coach.core.flag import Scope
from coach.core.instant import parse_instant
from coach.core.planned_week import week_monday
from coach.core.prescription import DecisionInForce
from coach.core.program.form import ProgramForm
from coach.services.history import read_history
from coach.services.leave_warning import leave_warning_decisions, plan_acknowledgements
from coach.store import decisions, programs, week_plans
from coach.store.connection import Connection

_DAY = datetime.timedelta(days=1)


def rung_decisions(
    conn: Connection, on: datetime.date | None = None, zone: datetime.tzinfo = datetime.UTC
) -> tuple[DecisionInForce, ...]:
    """The `ladder_rung` Decisions in force, each dated by the day it was recorded on in the
    athlete's timezone."""
    return tuple(
        DecisionInForce(
            id=str(row["id"]),
            kind=str(row["kind"]),
            session_id=cast(str | None, row["session_id"]),
            exercise_id=cast(str | None, row["exercise_id"]),
            params=cast(Mapping[str, object], row["params"]),
            on=parse_instant(str(row["recorded_at"])).astimezone(zone).date(),
        )
        for row in decisions.in_force(conn, None if on is None else on.isoformat())
        if row["kind"] == "ladder_rung"
    )


def standing_rungs(
    form: ProgramForm, found: Sequence[DecisionInForce]
) -> dict[tuple[str, str], int]:
    """Each ladder line's standing rung, keyed on (session, the line's key)."""
    return {
        (session.id, line.exercise): standing_rung(
            found, ladder, session_id=session.id, line_key=line.exercise, adopted=None
        ).index
        for session in form.sessions
        for line in session.lines
        if (ladder := line.scheme.ladder) is not None
    }


def ladder_reads(
    conn: Connection, *, units: Units, on: datetime.date, zone: datetime.tzinfo = datetime.UTC
) -> tuple[LadderRead, ...]:
    """Every ladder line of the version in force as the exposures logged up to `on` leave it."""
    version = programs.latest(conn)
    if version is None:
        return ()
    found = rung_decisions(conn, on, zone)
    adopted = datetime.date.fromisoformat(version.adopted[:10])
    exposures = read_history(conn, units).lifting
    plan = week_plans.latest_through(conn, week_monday(on).isoformat())
    monday = None if plan is None else datetime.date.fromisoformat(str(plan["week"]))
    frozen = () if plan is None else plan_acknowledgements(conn, str(plan["id"]))
    acknowledgements = (*frozen, *leave_warning_decisions(conn, on))
    return tuple(
        ladder_read(
            ladder,
            standing_rung(
                found, ladder, session_id=session.id, line_key=line.exercise, adopted=adopted
            ),
            exposures,
            scope=Scope("line", monday, session_id=session.id, exercise_id=line.exercise),
            before=on + _DAY,
            acknowledgements=acknowledgements,
        )
        for session in version.form.sessions
        for line in session.lines
        if (ladder := line.scheme.ladder) is not None
    )
