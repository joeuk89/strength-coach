"""Each routine as the approved WeekPlan that wrote it projects it: what a push sends, what a
re-run compares with live, and what import finds drift against (ADR 0011)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from coach.core.config import Units
from coach.core.hevy_actions import STANDING_CADENCES
from coach.core.mirror import FolderRole
from coach.core.program.form import Session
from coach.core.routine_projection import FrozenLine, SessionRoutine, project_routine
from coach.store import exercises, mirrors, niggles, programs, week_plans
from coach.store.connection import Connection
from coach.store.rows import Row

type Json = dict[str, object]


@dataclass(frozen=True)
class SessionFacts:
    """What a routine needs of its session beyond the frozen rows: the title, the authored lines
    and whether it lives in the Standing folder."""

    session: Session
    standing: bool


def session_facts(conn: Connection, plan: Mapping[str, object]) -> dict[str, SessionFacts]:
    """Every session as it stood when the plan was approved: the version then in force and
    every niggle's rehab session. A later adopt never changes what the plan projects."""
    version = programs.in_force_at(conn, str(plan["approved_at"]))
    facts: dict[str, SessionFacts] = {}
    if version is not None:
        for session in version.form.sessions:
            facts[session.id] = SessionFacts(session, session.cadence in STANDING_CADENCES)
    for rehab in niggles.every_rehab_session(conn):
        facts[rehab.id] = SessionFacts(rehab, standing=True)
    return facts


def projection(
    conn: Connection,
    plan: Mapping[str, object],
    session_id: str,
    facts: SessionFacts,
    units: Units,
) -> Json:
    """The session's routine body from the plan's frozen lines on its first planned date."""
    rows = [
        r for r in week_plans.prescriptions(conn, str(plan["id"])) if r["session_id"] == session_id
    ]
    first = min(str(r["date"]) for r in rows)
    folders = {f.role: f.hevy_id for f in mirrors.folders(conn)}
    library = exercises.every(conn)
    session = SessionRoutine(
        title=facts.session.title,
        folder_id=folders[folder_role(facts)],
        week_line=f"Week of {plan['week']}, rotation week {plan['position']}",
        authored=facts.session.lines,
        lines=[_frozen(r) for r in rows if r["date"] == first],
        names={str(row["id"]): str(row["name"]) for row in library},
    )
    templates = {
        str(row["id"]): str(row["hevy_template_id"]) for row in library if row["hevy_template_id"]
    }
    return project_routine(session, templates, units)


def folder_role(facts: SessionFacts) -> FolderRole:
    return "standing" if facts.standing else "program"


def _frozen(row: Row) -> FrozenLine:
    return FrozenLine(
        str(row["exercise_id"]),
        cast(list[Mapping[str, object]], row["set_groups"]),
        cast(list[Mapping[str, object]], row["steps"]),
    )
