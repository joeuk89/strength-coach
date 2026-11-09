"""The cadence signals open at a date: each line in force read over the last two closed Blocks
(docs/spec/goals.md, "Cadence signals")."""

import datetime
from typing import cast

from coach.core.cadence import BlockSpan, CadenceRead, cadence_signal
from coach.core.config import Units
from coach.core.flag import Flag, leave
from coach.core.planned_week import week_monday
from coach.core.program.form import Line, ProgramForm
from coach.services.closed_weeks import ClosedWeeks
from coach.services.history import read_history
from coach.services.ladders import rung_decisions, standing_line
from coach.services.leave_warning import leave_warning_decisions
from coach.store import programs, week_plans
from coach.store.connection import Connection

_DAY = datetime.timedelta(days=1)


def closed_spans(closed: ClosedWeeks) -> tuple[BlockSpan, ...]:
    """Every closed Block as its dates: from its opening to the day before the next opens."""
    return tuple(
        BlockSpan(block.id, block.opened, following.opened - _DAY)
        for block, following in zip(closed.blocks, closed.blocks[1:], strict=False)
        if block.closed_by is not None
    )


def cadence_signals(
    conn: Connection, closed: ClosedWeeks, *, units: Units, on: datetime.date, zone: datetime.tzinfo
) -> tuple[Flag, ...]:
    """Each signal left by a `leave_warning` Decision in force on `on`; none once a version is
    adopted after the closed Block's end, since a new version clears them."""
    spans = closed_spans(closed)
    version = programs.latest(conn)
    if len(spans) < 2 or version is None:
        return ()
    before, last = spans[-2:]
    answered = programs.in_force_at(conn, f"{last.end.isoformat()}T23:59:59")
    if answered is not None and version.sequence > answered.sequence:
        return ()
    forms = [_form_at(conn, span) for span in (before, last)]
    adherence = _adherence(closed, before, last)
    exposures = read_history(conn, units).lifting
    left = leave_warning_decisions(conn, on)
    rungs = rung_decisions(conn, zone, on)
    found: list[Flag] = []
    for session_id, line in _lines(version.form):
        if any(
            form is None or _scheme_of(form, line.exercise) != line.scheme.name for form in forms
        ):
            continue
        standing, counted = standing_line(line, session_id, rungs, exposures)
        read = CadenceRead(
            line,
            (before, last),
            [e for e in counted if e.exercise_id == standing.exercise],
            adherence,
            _capped(conn, closed, last, line) if line.scheme.name == "top_backoff" else (),
            session_id,
            standing,
        )
        flag = cadence_signal(read)
        if flag is not None:
            found.append(leave(flag, left))
    return tuple(found)


def _lines(form: ProgramForm) -> list[tuple[str, Line]]:
    """The first lifting line of each exercise: a signal is per exercise."""
    seen: dict[str, tuple[str, Line]] = {}
    for session in form.sessions:
        if session.kind != "lifting":
            continue
        for line in session.lines:
            seen.setdefault(line.exercise, (session.id, line))
    return list(seen.values())


def _form_at(conn: Connection, span: BlockSpan) -> ProgramForm | None:
    version = programs.in_force_at(conn, f"{span.end.isoformat()}T23:59:59")
    return None if version is None else version.form


def _scheme_of(form: ProgramForm, exercise_id: str) -> str | None:
    line = form.first_line(exercise_id)
    return None if line is None else line.scheme.name


def _adherence(closed: ClosedWeeks, *spans: BlockSpan) -> float | None:
    weeks = [w for w in closed.weeks if w.ordinary and any(s.holds(w.monday) for s in spans)]
    planned = sum(w.adherence_planned for w in weeks)
    return sum(w.adherence_trained for w in weeks) / planned if planned else None


def _capped(conn: Connection, closed: ClosedWeeks, span: BlockSpan, line: Line) -> list[bool]:
    """Per Prescription of the line frozen in the closed Block's ordinary weeks, whether the
    one-row cap set its top."""
    found: list[bool] = []
    for week in closed.weeks:
        if not week.ordinary or not span.holds(week.monday):
            continue
        plan = week_plans.in_force(conn, week_monday(week.monday).isoformat())
        if plan is None:
            continue
        for row in week_plans.prescriptions(conn, str(plan["id"])):
            if row["exercise_id"] == line.exercise:
                steps = cast(list[dict[str, object]], row["steps"])
                found.append(any(step.get("cause") == "one_row_cap" for step in steps))
    return found
