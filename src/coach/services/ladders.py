"""Where each `exercise_ladder` line of the version in force stands (ADR 0023): what the check-in
card, the progress view and the pages read, from the same rule `plan draft` prescribes by."""

import datetime
from collections.abc import Sequence

from coach.core.config import Units
from coach.core.exercise_ladder import (
    LadderRead,
    LineRef,
    ladder_read,
    rung_line,
    standing_rung,
)
from coach.core.flag import Scope
from coach.core.planned_week import week_monday
from coach.core.prescription import DecisionInForce
from coach.core.program.form import Line, ProgramForm
from coach.services.history import read_history
from coach.services.leave_warning import leave_warning_decisions, plan_acknowledgements
from coach.store import decisions, programs, week_plans
from coach.store.connection import Connection

_DAY = datetime.timedelta(days=1)


def rung_decisions(
    conn: Connection, zone: datetime.tzinfo, on: datetime.date | None = None
) -> tuple[DecisionInForce, ...]:
    """The `ladder_rung` Decisions in force, each dated by the day it was recorded on in the
    athlete's timezone."""
    return decisions.in_force_dated(conn, on, ("ladder_rung",), zone)


def standing_rungs(form: ProgramForm, found: Sequence[DecisionInForce]) -> dict[LineRef, int]:
    """Each ladder line's standing rung."""
    return {
        (ref := LineRef(session.id, line.exercise)): standing_rung(
            found, ladder, line=ref, adopted=None
        ).index
        for session in form.sessions
        for line in session.lines
        if (ladder := line.ladder) is not None
    }


def standing_line(
    line: Line, session_id: str, found: Sequence[DecisionInForce]
) -> tuple[Line, datetime.date | None]:
    """The line as its standing rung prescribes it and the date its exposures count from: a
    rung's exercise can be an earlier rung's too, so only its start tells their histories apart."""
    ladder = line.ladder
    if ladder is None:
        return line, None
    standing = standing_rung(found, ladder, line=LineRef(session_id, line.exercise), adopted=None)
    return rung_line(line, ladder, standing.index), standing.since


def ladder_reads(
    conn: Connection, *, units: Units, on: datetime.date, zone: datetime.tzinfo
) -> tuple[LadderRead, ...]:
    """Every ladder line of the version in force as the exposures logged up to `on` leave it."""
    version = programs.latest(conn)
    if version is None:
        return ()
    found = rung_decisions(conn, zone, on)
    adopted = version.adopted_on
    exposures = read_history(conn, units).lifting
    plan = week_plans.latest_through(conn, week_monday(on).isoformat())
    monday = None if plan is None else datetime.date.fromisoformat(str(plan["week"]))
    frozen = () if plan is None else plan_acknowledgements(conn, str(plan["id"]))
    acknowledgements = (*frozen, *leave_warning_decisions(conn, on))
    return tuple(
        ladder_read(
            ladder,
            standing_rung(found, ladder, line=LineRef(session.id, line.exercise), adopted=adopted),
            exposures,
            scope=Scope("line", monday, session_id=session.id, exercise_id=line.exercise),
            before=on + _DAY,
            acknowledgements=acknowledgements,
        )
        for session in version.form.sessions
        for line in session.lines
        if (ladder := line.ladder) is not None
    )
