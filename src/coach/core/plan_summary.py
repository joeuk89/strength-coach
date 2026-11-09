"""What the athlete approves, as the dry run and the approval prompt show it: the week's sessions
and lines, its overrides and its flags (ADR 0006). A first approval shows the checked Draft; a
resume shows the WeekPlan's frozen rows (docs/spec/verbs.md, "Re-run safety")."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.config import Units
from coach.core.flag import Flag
from coach.core.frozen_prescription import frozen_groups
from coach.core.plan_check import CheckedPlan
from coach.core.planned_week import RotationPosition
from coach.core.prescription import PlanOverride
from coach.core.routine_projection import RungKey, authored_exercise

type Json = Mapping[str, object]
type NextRungs = Mapping[str, Mapping[RungKey, str]]


@dataclass(frozen=True)
class SummaryLine:
    exercise_id: str
    set_groups: Sequence[Json]
    change: str
    next_rung: str | None = None


@dataclass(frozen=True)
class SummarySession:
    session_id: str
    date: datetime.date
    location: str
    lines: tuple[SummaryLine, ...]


@dataclass(frozen=True)
class PlanSummary:
    week: datetime.date
    position: RotationPosition
    supersedes: str | None
    sessions: tuple[SummarySession, ...]
    overrides: tuple[PlanOverride, ...]
    flags: tuple[Flag, ...]


def fresh_summary(checked: CheckedPlan, units: Units, next_rungs: NextRungs) -> PlanSummary:
    """`next_rungs` are each session's next rung labels, keyed on the authored exercise
    and rung."""
    draft = checked.draft
    return PlanSummary(
        week=draft.week,
        position=draft.position,
        supersedes=draft.supersedes,
        sessions=tuple(
            SummarySession(
                prescribed.session.session_id,
                prescribed.session.date,
                prescribed.session.location,
                tuple(
                    SummaryLine(
                        line.exercise_id,
                        frozen_groups(line.groups, units),
                        line.change,
                        _next_rung(
                            next_rungs,
                            prescribed.session.session_id,
                            line.exercise_id,
                            [step.to_json() for step in line.steps],
                            line.rung,
                        ),
                    )
                    for line in prescribed.lines
                ),
            )
            for prescribed in draft.sessions
        ),
        overrides=draft.overrides,
        flags=checked.flags,
    )


def frozen_summary(
    *,
    week: datetime.date,
    position: str,
    supersedes: str | None,
    rows: Sequence[Json],
    overrides: Sequence[PlanOverride],
    locations: Mapping[str, str],
    next_rungs: NextRungs,
) -> PlanSummary:
    """The WeekPlan as its prescription rows froze it, in their order. The rows carry no
    location, so each session's comes from `locations` with the plan's overrides folded in, and
    no ladder, so a line's next rung comes from `next_rungs`, as in `fresh_summary`. A flag is
    frozen on every line it bears on; the summary shows it once."""
    days: dict[tuple[datetime.date, str], list[Json]] = {}
    for row in rows:
        day = datetime.date.fromisoformat(str(row["date"]))
        days.setdefault((day, str(row["session_id"])), []).append(row)
    sessions = tuple(
        SummarySession(
            session_id,
            day,
            _location(session_id, day, locations, overrides),
            tuple(_line(row, next_rungs) for row in found),
        )
        for (day, session_id), found in days.items()
    )
    flags: dict[str, Flag] = {}
    for row in rows:
        for document in cast(list[Json], row["flags"]):
            flag = Flag.from_json(document)
            flags.setdefault(flag.key, flag)
    return PlanSummary(
        week=week,
        position=RotationPosition(position, "plan_in_force"),
        supersedes=supersedes,
        sessions=sessions,
        overrides=tuple(overrides),
        flags=tuple(sorted(flags.values(), key=lambda f: f.severity != "violation")),
    )


def _line(row: Json, next_rungs: NextRungs) -> SummaryLine:
    exercise_id = str(row["exercise_id"])
    return SummaryLine(
        exercise_id,
        cast(list[Json], row["set_groups"]),
        str(row["change"]),
        _next_rung(
            next_rungs,
            str(row["session_id"]),
            exercise_id,
            cast(list[Json], row["steps"]),
            cast(int | None, row["rung"]),
        ),
    )


def _next_rung(
    next_rungs: NextRungs,
    session_id: str,
    exercise_id: str,
    steps: Sequence[Json],
    rung: int | None,
) -> str | None:
    return next_rungs.get(session_id, {}).get((authored_exercise(exercise_id, steps), rung))


def _location(
    session_id: str,
    day: datetime.date,
    locations: Mapping[str, str],
    overrides: Sequence[PlanOverride],
) -> str:
    """As the plan Draft placed the session: a one-off week's location over the session's own,
    then a relocate; an added session at its own location, else the week's."""
    base = locations.get(session_id, "")
    week = next((o.params.get("location") for o in overrides if o.kind == "one_off_week"), None)
    added = next(
        (
            o
            for o in overrides
            if o.kind == "add_session" and o.session_id == session_id and o.date == day
        ),
        None,
    )
    if added is not None:
        found = added.params.get("location", week)
        return found if isinstance(found, str) else base
    found = week if isinstance(week, str) else base
    for override in overrides:
        if override.kind == "relocate_session" and override.session_id == session_id:
            found = str(override.params["location"])
    return found
