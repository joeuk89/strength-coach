"""`plan draft`: derive the week's prescriptions and render the plan Draft (docs/spec/verbs.md,
"Drafts written by the engine"; docs/spec/prescription.md)."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.activity_rules import quality_stack, status_span_drops
from coach.core.clock import Clock
from coach.core.closed_week.block import block_ceiling_exceeded
from coach.core.closed_week.dose import (
    dose_under_target,
    minimum_week_floor,
    session_dose_high,
)
from coach.core.closed_week.match import QUALITY_RPE
from coach.core.config import Config
from coach.core.errors import Invalid
from coach.core.fatigue import light_week_flags
from coach.core.flag import Flag
from coach.core.instant import parse_instant
from coach.core.kit import KitFiles
from coach.core.load import LoadMode
from coach.core.overrides import override_conflicts
from coach.core.plan_draft import AthleteNote, PlanDraft
from coach.core.planned_week import RotationPosition, choose_sessions, planned_sessions
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    ExerciseFacts,
    PlannedSession,
    PlanOverride,
    PrescribeRequest,
    ProgramVersion,
    SessionPrescription,
)
from coach.core.program.form import ProgramForm
from coach.render.plan_draft import plan_draft as render_plan_draft
from coach.services.closed_weeks import (
    ClosedWeeks,
    WeekLog,
    muscle_map,
    parked_sessions,
    status_spans,
)
from coach.services.fatigue import Fatigue
from coach.services.history import read_history
from coach.services.previous_plans import second_week_flags
from coach.services.racks import racks_by_location
from coach.services.rotation import default_week, rotation_position
from coach.store import (
    check_ins,
    decisions,
    exercises,
    goals,
    niggles,
    notes,
    programs,
    week_plans,
)
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
    overrides: Sequence[PlanOverride] = (),
    position: str | None = None,
) -> PlanDraftResult:
    """`position` is the rotation week a Draft confirmed; without one the inferred week stands
    unconfirmed."""
    version = _in_force(conn)
    monday = week or default_week(conn, clock.today())
    if monday.weekday() != 0:
        raise Invalid("invalid_argument", f"--week {monday} is not a Monday")
    inferred = rotation_position(conn, version, monday)
    if position is not None and position not in version.form.schedule.rotation:
        raise Invalid("invalid_argument", f"rotation week {position!r} is not in the rotation")
    rotation = inferred if position is None else RotationPosition(position, inferred.source)
    rehab = niggles.open_rehab_sessions(conn)
    spans = status_spans(conn)
    log = WeekLog(conn, config.athlete.units)
    closed = log.closed_by(check_ins.current_windows(conn))
    hard_week_count = closed.open_block.hard_weeks if closed.open_block else 0
    planned = choose_sessions(
        planned_sessions(
            version.form,
            position=rotation.week,
            monday=monday,
            rehab=rehab,
            spans=spans,
            parked=parked_sessions(conn, monday),
        ),
        overrides,
        form=version.form,
        monday=monday,
        rehab=rehab,
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
                overrides=tuple(overrides),
                decisions=_decisions(conn, session),
                niggle_constraints=constraints,
                status_spans=spans,
                hard_week_count=hard_week_count,
            )
        )
        for session in planned
    )
    in_force = week_plans.in_force(conn, monday.isoformat())
    standing = Fatigue(conn, log).standing()
    draft = PlanDraft(
        week=monday,
        position=rotation,
        sessions=sessions,
        notes=_notes_since_last_approved(conn),
        supersedes=None if in_force is None else str(in_force["id"]),
        overrides=tuple(overrides),
        conflicts=override_conflicts(overrides, monday),
        confirmed=position is not None,
        second_week=second_week_flags(
            conn,
            sessions,
            overrides,
            monday=monday,
            racks=racks,
            units=config.athlete.units,
        ),
        week_checks=(
            *_week_checks(
                conn, version.form, closed, sessions, overrides, monday=monday, today=clock.today()
            ),
            *light_week_flags(
                overrides,
                standing.proposal if standing else None,
                hard_weeks=hard_week_count,
                deload=version.form.deload,
                monday=monday,
            ),
            *quality_stack(
                sessions,
                quality=_quality_conditioning(version.form),
                patterns={
                    str(r["id"]): cast(str | None, r["pattern"]) for r in exercises.every(conn)
                },
            ),
            *status_span_drops(sessions, spans),
        ),
        hard_week_count=hard_week_count,
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


def _week_checks(
    conn: Connection,
    form: ProgramForm,
    closed: ClosedWeeks,
    sessions: Sequence[SessionPrescription],
    overrides: Sequence[PlanOverride],
    *,
    monday: datetime.date,
    today: datetime.date,
) -> tuple[Flag, ...]:
    """The plan warnings and the Block violation that read the closed weeks (docs/spec/week.md,
    "The Block" and "Dose")."""
    muscles = muscle_map(conn)
    found: list[Flag | None] = [dose_under_target(closed.weeks, monday)]
    found.extend(session_dose_high(session, muscles) for session in sessions)
    block = closed.open_block
    if block is not None and form.deload is not None:
        found.append(
            block_ceiling_exceeded(
                block,
                form.deload.hard_weeks_ceiling,
                monday,
                light_week=any(o.kind == "light_week" for o in overrides),
                declined=any(
                    row["kind"] == "decline_ceiling"
                    and cast(Mapping[str, object], row["params"]).get("block") == block.id
                    for row in decisions.in_force(conn, today.isoformat())
                ),
            )
        )
    minimum = next((o for o in overrides if o.kind == "minimum_week"), None)
    if minimum is not None:
        kept = cast(Sequence[str], minimum.params.get("keep", ()))
        found.append(minimum_week_floor(sessions, kept, _priority_lifts(conn), monday))
    return tuple(flag for flag in found if flag is not None)


def _quality_conditioning(form: ProgramForm) -> frozenset[str]:
    """The conditioning sessions whose scheme targets quality work (rn:running-load.6)."""
    return frozenset(
        s.id
        for s in form.sessions
        if s.kind == "conditioning"
        and s.scheme is not None
        and _number(s.scheme.params.get("rpe_target")) >= QUALITY_RPE
    )


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0


def _priority_lifts(conn: Connection) -> tuple[str, ...]:
    goal_id = goals.current_id(conn)
    stored = goals.get(conn, goal_id) if goal_id else None
    return stored.goal.priority_lifts if stored else ()


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
