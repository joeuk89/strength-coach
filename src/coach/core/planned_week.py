"""The planned sessions of a week and the rotation position it is planned against
(docs/spec/week.md, "Match"; docs/spec/prescription.md, "The pipeline")."""

import datetime
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from typing import Literal, cast

from coach.core.errors import Invalid
from coach.core.prescription import PlannedSession, PlanOverride, StatusSpan
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
    parked: Collection[str] = (),
) -> tuple[PlannedSession, ...]:
    """Weekly sessions on their weekday, a standing session once on the Monday (its window is
    the week), a daily session every day; a parked session is none of them (ADR 0010,
    "Lifecycle"). A `no_training` span over the whole week plans nothing."""
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
    return tuple(sorted((s for s in found if s.session_id not in parked), key=lambda s: s.date))


def choose_sessions(
    planned: Sequence[PlannedSession],
    overrides: Sequence[PlanOverride],
    *,
    form: ProgramForm,
    monday: datetime.date,
    rehab: Sequence[Session] = (),
) -> tuple[PlannedSession, ...]:
    """The pre-step: the plan's week and session overrides choose which sessions derive and
    where, and never touch a number (docs/spec/prescription.md, "The pipeline")."""
    by_kind = {o.kind: o for o in overrides if o.session_id is None}
    week_location = by_kind.get("one_off_week", PlanOverride("one_off_week")).params.get("location")
    added = [
        _added(o, form, rehab, week_location, monday) for o in overrides if o.kind == "add_session"
    ]
    _check_targets(planned, added, overrides)
    chosen = list(planned)
    if "minimum_week" in by_kind:
        keep = cast(tuple[str, ...], by_kind["minimum_week"].params["keep"])
        chosen = [s for s in chosen if s.session_id in keep]
    if isinstance(week_location, str):
        chosen = [replace(s, location=week_location) for s in chosen]
    for override in overrides:
        chosen = _apply(chosen, override, monday)
    return tuple(sorted((*chosen, *added), key=lambda s: s.date))


def _check_targets(
    planned: Sequence[PlannedSession],
    added: Sequence[PlannedSession],
    overrides: Sequence[PlanOverride],
) -> None:
    """A line override may name a session `add_session` brings in; a session override may not,
    since the add already carries its own date and location."""
    every = (*planned, *added)
    lines = {(s.session_id, line.exercise) for s in every for line in s.lines}
    planned_ids = {s.session_id for s in planned}
    every_ids = {s.session_id for s in every}
    for override in overrides:
        session = override.session_id
        if session is None or override.kind == "add_session":
            continue
        targets = planned_ids if override.exercise_id is None else every_ids
        if session not in targets:
            raise Invalid(
                "invalid_argument",
                f"the {override.kind} override names {session}, which is not planned this week",
            )
        if override.exercise_id is not None and (session, override.exercise_id) not in lines:
            raise Invalid(
                "invalid_argument",
                f"the {override.kind} override names {override.exercise_id}, which is not a "
                f"line of {session}",
            )


def _apply(
    chosen: list[PlannedSession], override: PlanOverride, monday: datetime.date
) -> list[PlannedSession]:
    def on_session(planned: PlannedSession) -> bool:
        return planned.session_id == override.session_id

    match override.kind:
        case "drop_session":
            return [s for s in chosen if not on_session(s)]
        case "move_session":
            to = cast(datetime.date, override.params["to"])
            if not _in_week(to, monday):
                return [s for s in chosen if not on_session(s)]
            return [replace(s, date=to) if on_session(s) else s for s in chosen]
        case "relocate_session":
            location = str(override.params["location"])
            return [replace(s, location=location) if on_session(s) else s for s in chosen]
        case _:
            return chosen


def _added(
    override: PlanOverride,
    form: ProgramForm,
    rehab: Sequence[Session],
    week_location: object,
    monday: datetime.date,
) -> PlannedSession:
    """Any session of the version, a parked one included, or a rehab session; never a body
    the version lacks."""
    session_id = str(override.session_id)
    session = form.session(session_id) or next((r for r in rehab if r.id == session_id), None)
    if session is None:
        raise Invalid(
            "draft_ref_unresolved",
            f"add_session names {session_id}, which is no session of the version or a niggle",
        )
    on = cast(datetime.date, override.date)
    if not _in_week(on, monday):
        raise Invalid(
            "invalid_argument",
            f"add_session dates {session_id} on {on.isoformat()}, outside the week of "
            f"{monday.isoformat()}",
        )
    planned = _planned(form, session, on, session.cadence or "weekly")
    location = override.params.get("location", week_location)
    return replace(planned, location=location) if isinstance(location, str) else planned


def _in_week(day: datetime.date, monday: datetime.date) -> bool:
    return monday <= day < monday + datetime.timedelta(days=DAYS_IN_WEEK)


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
