"""The planned sessions of a week and the rotation position it is planned against
(docs/spec/week.md, "Match"; docs/spec/prescription.md, "The pipeline")."""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from coach.core.prescription import PlannedSession, StatusSpan
from coach.core.program.form import WEEKDAYS, ProgramForm, Session

DAYS_IN_WEEK = 7

type PositionSource = Literal["plan_in_force", "previous_plan", "program_adopt"]


@dataclass(frozen=True)
class RotationPosition:
    week: str
    source: PositionSource


def week_monday(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def infer_position(
    rotation: Sequence[str],
    *,
    adopted: str,
    previous: str | None = None,
    in_force: str | None = None,
) -> RotationPosition:
    """The week's own approved plan keeps its position; otherwise the rotation week after the
    last approved plan of the open Block; otherwise the week the version was adopted at."""
    if in_force is not None and in_force in rotation:
        return RotationPosition(in_force, "plan_in_force")
    if previous is not None and previous in rotation:
        following = rotation[(rotation.index(previous) + 1) % len(rotation)]
        return RotationPosition(following, "previous_plan")
    return RotationPosition(adopted, "program_adopt")


def planned_sessions(
    form: ProgramForm,
    *,
    position: str,
    monday: datetime.date,
    rehab: Sequence[Session] = (),
    spans: Sequence[StatusSpan] = (),
) -> tuple[PlannedSession, ...]:
    """Weekly sessions on their weekday, a standing session once on the Monday (its window is
    the week), a daily session every day. A `no_training` span over the whole week plans
    nothing."""
    days = [monday + datetime.timedelta(days=n) for n in range(DAYS_IN_WEEK)]
    if any(span.kind == "no_training" and all(span.covers(d) for d in days) for span in spans):
        return ()
    found: list[PlannedSession] = []
    for weekday, session_id in form.schedule.weeks.get(position, {}).items():
        session = form.session(session_id)
        if session is not None:
            found.append(_planned(form, session, days[WEEKDAYS.index(weekday)], "weekly"))
    for session in (*form.sessions, *rehab):
        if session.cadence == "standing":
            found.append(_planned(form, session, monday, "standing"))
        elif session.cadence == "daily":
            found.extend(_planned(form, session, day, "daily") for day in days)
    return tuple(sorted(found, key=lambda s: s.date))


def _planned(
    form: ProgramForm, session: Session, day: datetime.date, cadence: str
) -> PlannedSession:
    return PlannedSession(
        session_id=session.id,
        date=day,
        location=session.location or form.location,
        kind=session.kind,
        lines=session.lines,
        cadence=cadence,
        tier=session.tier,
    )
