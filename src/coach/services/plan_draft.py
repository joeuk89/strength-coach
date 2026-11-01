"""`plan draft`: derive the week's prescriptions and render the plan Draft (docs/spec/verbs.md,
"Drafts written by the engine"; docs/spec/prescription.md)."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.clock import Clock
from coach.core.config import Config
from coach.core.errors import Invalid
from coach.core.instant import parse_instant
from coach.core.kit import KitFiles
from coach.core.load import LoadMode
from coach.core.plan_draft import AthleteNote, PlanDraft
from coach.core.planned_week import planned_sessions
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    ExerciseFacts,
    PlannedSession,
    PrescribeRequest,
    ProgramVersion,
    StatusSpan,
)
from coach.render.plan_draft import plan_draft as render_plan_draft
from coach.services.history import read_history
from coach.services.racks import racks_by_location
from coach.services.rotation import default_week, rotation_position
from coach.store import decisions, exercises, niggles, notes, programs, readings, week_plans
from coach.store.connection import Connection

# The Decision kinds prescribe reads (prescription.md, "What prescribe is handed").
PRESCRIBING_DECISIONS = ("override", "safety_ceiling", "training_max")


@dataclass(frozen=True)
class PlanDraftResult:
    draft: PlanDraft
    text: str


def plan_draft(
    conn: Connection,
    *,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
    week: datetime.date | None = None,
) -> PlanDraftResult:
    version = _in_force(conn)
    monday = week or default_week(conn, clock.today())
    if monday.weekday() != 0:
        raise Invalid("invalid_argument", f"--week {monday} is not a Monday")
    position = rotation_position(conn, version, monday)
    rehab = niggles.open_rehab_sessions(conn)
    spans = _status_spans(conn)
    planned = planned_sessions(
        version.form, position=position.week, monday=monday, rehab=rehab, spans=spans
    )
    locations = {*version.form.locations(), *(s.location for s in planned)}
    racks = racks_by_location(config, kits, locations)
    history = read_history(conn, config.athlete.units)
    program = ProgramVersion(version.form, _exercise_facts(conn))
    constraints = niggles.open_constraints(conn)
    sessions = tuple(
        prescribe(
            PrescribeRequest(
                version=program,
                exposures=history.exposures,
                racks=racks,
                planned=session,
                trained=history.trained,
                decisions=_decisions(conn, session),
                niggle_constraints=constraints,
                status_spans=spans,
            )
        )
        for session in planned
    )
    in_force = week_plans.in_force(conn, monday.isoformat())
    draft = PlanDraft(
        week=monday,
        position=position,
        sessions=sessions,
        notes=_notes_since_last_approved(conn),
        supersedes=None if in_force is None else str(in_force["id"]),
    )
    return PlanDraftResult(draft, render_plan_draft(draft, units=config.athlete.units))


def _in_force(conn: Connection) -> programs.VersionRow:
    version = programs.latest(conn)
    if version is None:
        raise Invalid("invalid_argument", "no Program version is adopted yet; run program adopt")
    return version


def _exercise_facts(conn: Connection) -> Mapping[str, ExerciseFacts]:
    return {
        str(row["id"]): ExerciseFacts(
            cast(LoadMode, row["load_mode"]),
            str(row["equipment_kind"]),
            cast(str | None, row["pattern"]),
        )
        for row in exercises.every(conn)
    }


def _decisions(conn: Connection, session: PlannedSession) -> tuple[DecisionInForce, ...]:
    return tuple(
        DecisionInForce(
            id=str(row["id"]),
            kind=str(row["kind"]),
            session_id=cast(str | None, row["session_id"]),
            exercise_id=cast(str | None, row["exercise_id"]),
            params=cast(Mapping[str, object], row["params"]),
        )
        for row in decisions.in_force(conn, session.date.isoformat())
        if row["kind"] in PRESCRIBING_DECISIONS
    )


def _status_spans(conn: Connection) -> tuple[StatusSpan, ...]:
    return tuple(
        StatusSpan(
            str(row["kind"]),
            datetime.date.fromisoformat(str(row["from_date"])),
            None if row["to_date"] is None else datetime.date.fromisoformat(str(row["to_date"])),
        )
        for row in readings.live(conn, "status_span")
    )


def _notes_since_last_approved(conn: Connection) -> tuple[AthleteNote, ...]:
    """Every Athlete note recorded after the last WeekPlan was approved (check-in.md,
    "Athlete notes")."""
    last = week_plans.last_approved(conn)
    since = None if last is None else parse_instant(str(last["approved_at"]))
    return tuple(
        AthleteNote(
            datetime.date.fromisoformat(str(row["date"])),
            str(row["text"]),
            cast(str | None, row["about"]),
        )
        for row in notes.every(conn)
        if since is None or parse_instant(str(row["recorded_at"])) > since
    )
