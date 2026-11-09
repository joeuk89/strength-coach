"""`plan apply`: the one plan check and the Write plan hash offline with `--dry-run` (ADR 0006),
and the push: the WeekPlan born approved, then the Hevy writes, each read back and mapped
(ADR 0011, "Push"; docs/spec/verbs.md, "Re-run safety")."""

import datetime
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.clock import Clock
from coach.core.config import Config, Units
from coach.core.draft_fields import draft_hash
from coach.core.errors import Invalid, Refused
from coach.core.flag import Acknowledgement, Flag
from coach.core.frozen_prescription import frozen_groups
from coach.core.hevy_actions import (
    HevyActions,
    ProjectedSession,
    frozen_sessions,
    hevy_actions,
    projected_sessions,
)
from coach.core.instant import utc_instant
from coach.core.kit import KitFiles
from coach.core.plan_check import CheckedPlan, TemplateFacts, check_plan
from coach.core.plan_input import PlanInput, parse_plan_input
from coach.core.plan_summary import PlanSummary, fresh_summary, frozen_summary
from coach.core.prescription import PlanOverride
from coach.core.program.checks import TEMPLATE_COLUMNS
from coach.core.write_plan import (
    moved_routines,
    override_params,
    resumed_write_plan_hash,
    write_plan_hash,
)
from coach.hevy.protocol import HevyClient
from coach.services.leave_warning import leave_warning_decisions
from coach.services.plan_draft import plan_draft
from coach.services.projections import next_rungs, session_facts
from coach.services.routine_push import Push, RoutineOutcome, guard
from coach.store import exercises, mirrors, niggles, programs, routine_map, week_plans
from coach.store.connection import Connection
from coach.store.programs import VersionRow
from coach.store.rows import Row
from coach.store.transaction import transaction


@dataclass(frozen=True)
class CheckedDraft:
    checked: CheckedPlan
    acknowledgements: tuple[Acknowledgement, ...]
    templates: dict[str, TemplateFacts] | None


@dataclass(frozen=True)
class DryRun:
    """`checked` is the Draft checked now, which a first approval freezes; a resume has none,
    since it shows and pushes the WeekPlan as it was frozen."""

    summary: PlanSummary
    actions: HevyActions
    write_plan_hash: str
    acknowledgements: tuple[Acknowledgement, ...] = ()
    resumes: str | None = None
    moved_routines: tuple[str, ...] = ()
    checked: CheckedPlan | None = None

    @property
    def flags(self) -> tuple[Flag, ...]:
        return self.summary.flags


def validate(
    conn: Connection,
    data: bytes,
    *,
    file: str,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
) -> CheckedDraft:
    """Every flag of the Draft re-derived now, left or not; a violation is reported, not raised."""
    found = parse_plan_input(data, file=file)
    return _validated(conn, found, config=config, kits=kits, clock=clock)


def _validated(
    conn: Connection,
    found: PlanInput,
    *,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
) -> CheckedDraft:
    drafted = plan_draft(
        conn,
        config=config,
        kits=kits,
        clock=clock,
        week=found.week,
        overrides=found.overrides,
        position=found.position,
    )
    templates = _templates(conn) if config.hevy is not None else None
    checked = check_plan(
        drafted.draft,
        acknowledgements=(*found.acknowledgements, *leave_warning_decisions(conn, found.week)),
        templates=templates,
    )
    return CheckedDraft(checked, found.acknowledgements, templates)


def dry_run(
    conn: Connection,
    data: bytes,
    *,
    file: str,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
) -> DryRun:
    found = parse_plan_input(data, file=file)
    approved = week_plans.with_draft(conn, found.week.isoformat(), draft_hash(data))
    if approved is not None:
        return _resumed(conn, approved, hevy=config.hevy is not None)
    validated = _validated(conn, found, config=config, kits=kits, clock=clock)
    checked = validated.checked
    if checked.violations:
        first = checked.violations[0]
        raise Invalid(
            first.code,
            f"the plan has {len(checked.violations)} violation(s); change the fact behind each "
            "and run the dry run again",
            {"flags": [flag.to_summary() for flag in checked.flags]},
        )
    actions = _actions(conn, checked, validated.templates)
    digest = write_plan_hash(
        checked.draft,
        acknowledgements=validated.acknowledgements,
        actions=actions,
        routine_versions={r.hevy_id: r.updated_at for r in mirrors.routines(conn)},
        units=config.athlete.units,
    )
    return DryRun(
        fresh_summary(checked, config.athlete.units, next_rungs(conn, programs.latest(conn))),
        actions,
        digest,
        validated.acknowledgements,
        checked=checked,
    )


def _resumed(conn: Connection, approved: Row, *, hevy: bool) -> DryRun:
    """The same Draft already approved: the dry run shows and pushes the frozen WeekPlan under
    the approved hash, or a new one when a touched routine moved in Hevy since approval."""
    plan_id = str(approved["id"])
    rows = week_plans.prescriptions(conn, plan_id)
    version = programs.in_force_at(conn, str(approved["approved_at"]))
    summary = frozen_summary(
        week=datetime.date.fromisoformat(str(approved["week"])),
        position=str(approved["position"]),
        supersedes=week_plans.superseded(conn, plan_id),
        rows=rows,
        overrides=week_plans.stored_overrides(conn, plan_id),
        locations=_locations(conn, version),
        next_rungs=next_rungs(conn, version),
    )
    actions = _frozen_actions(conn, approved, version, rows) if hevy else HevyActions()
    moved = moved_routines(
        actions.touched_routines,
        approved_at=str(approved["approved_at"]),
        imports=mirrors.routine_imports(conn),
        own_writes=routine_map.written_by(conn, plan_id),
    )
    versions = {r.hevy_id: r.updated_at for r in mirrors.routines(conn)}
    digest = resumed_write_plan_hash(
        str(approved["write_plan_hash"]), {routine: versions[routine] for routine in moved}
    )
    return DryRun(summary, actions, digest, resumes=plan_id, moved_routines=moved)


def _locations(conn: Connection, version: VersionRow | None) -> dict[str, str]:
    """Each session at its own location, else the default of the version in force at approval."""
    default = version.form.location if version else None
    sessions = (*niggles.every_rehab_session(conn), *(version.form.sessions if version else ()))
    return {s.id: s.location or default or "" for s in sessions}


def _frozen_actions(
    conn: Connection, approved: Row, version: VersionRow | None, rows: Sequence[Row]
) -> HevyActions:
    """The frozen WeekPlan's sessions against the routines, folders and templates as they are
    now. Every session the plan projects stays in force, so a resume never retires one."""
    facts = session_facts(conn, approved)
    projected = frozen_sessions(
        [(str(r["session_id"]), str(r["exercise_id"])) for r in rows],
        standing={s for s, f in facts.items() if f.standing},
    )
    return hevy_actions(
        projected,
        routine_map=routine_map.rows(conn),
        folders={folder.role for folder in mirrors.folders(conn)},
        sessions_in_force=_in_force(conn, version, projected),
        templates=_templates(conn),
    )


def _in_force(
    conn: Connection, version: VersionRow | None, projected: Sequence[ProjectedSession]
) -> set[str]:
    return {
        *(s.id for s in (version.form.sessions if version else ())),
        *(s.id for s in niggles.open_rehab_sessions(conn)),
        *(s.session_id for s in projected),
    }


def _actions(
    conn: Connection, checked: CheckedPlan, templates: dict[str, TemplateFacts] | None
) -> HevyActions:
    if templates is None:
        return HevyActions()
    version = programs.latest(conn)
    assert version is not None
    in_force = {s.id for s in (*version.form.sessions, *niggles.open_rehab_sessions(conn))}
    return hevy_actions(
        projected_sessions(checked.draft.sessions),
        routine_map=routine_map.rows(conn),
        folders={folder.role for folder in mirrors.folders(conn)},
        sessions_in_force=in_force,
        templates=templates,
    )


def _templates(conn: Connection) -> dict[str, TemplateFacts]:
    return {
        str(row["id"]): TemplateFacts(
            str(row["id"]),
            cast(str | None, row["hevy_template_id"]),
            {column: cast(str | None, row[column]) for column in TEMPLATE_COLUMNS},
        )
        for row in exercises.every(conn)
    }


@dataclass(frozen=True)
class ApplyResult:
    week_plan_id: str
    write_plan_hash: str
    resumed: bool
    routines: tuple[RoutineOutcome, ...]
    audit_lines: int


def apply(
    conn: Connection,
    client: HevyClient | None,
    data: bytes,
    *,
    file: str,
    expect: str | None,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
) -> ApplyResult:
    found = expected(conn, data, file=file, expect=expect, config=config, kits=kits, clock=clock)
    return push_approved(conn, client, data, found, config=config, clock=clock)


def expected(
    conn: Connection,
    data: bytes,
    *,
    file: str,
    expect: str | None,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
) -> DryRun:
    """The dry run, refused unless its hash is the one the athlete approved."""
    if expect is None:
        raise Refused(
            "expect_missing",
            "plan apply writes only the Write plan the athlete approved; run it with --dry-run "
            "and pass the hash with --expect",
        )
    found = dry_run(conn, data, file=file, config=config, kits=kits, clock=clock)
    if found.write_plan_hash != expect:
        raise Refused(
            "expect_mismatch",
            f"the Write plan is now {found.write_plan_hash}, not the approved {expect}; run "
            "plan apply --dry-run again for the athlete to approve",
        )
    return found


def push_approved(
    conn: Connection,
    client: HevyClient | None,
    data: bytes,
    found: DryRun,
    *,
    config: Config,
    clock: Clock,
) -> ApplyResult:
    """The WeekPlan is approved and frozen before the first Hevy call, so approval survives an
    unreachable Hevy, a guard's refusal and a failed push, and a re-run resumes it. The guards
    run before any write. `client` is None without a `[hevy]` table."""
    now = clock.now()
    plan_id = found.resumes or _approve(conn, found, data, config.athlete.units, now)
    plan = week_plans.by_id(conn, plan_id)
    if client is None:
        return ApplyResult(plan_id, found.write_plan_hash, found.resumes is not None, (), 0)
    guarded = guard(conn, client, found.actions)
    push = Push(conn, client, plan, session_facts(conn, plan), config.athlete.units, now)
    try:
        push.run(found.actions, guarded)
    except Invalid as error:
        raise Invalid(
            error.code,
            error.message,
            {**error.details, "audit_lines": push.audit_lines},
        ) from error
    return ApplyResult(
        plan_id,
        found.write_plan_hash,
        found.resumes is not None,
        tuple(push.outcomes),
        push.audit_lines,
    )


def _approve(
    conn: Connection, found: DryRun, data: bytes, units: Units, now: datetime.datetime
) -> str:
    assert found.checked is not None
    draft = found.checked.draft
    week = draft.week.isoformat()
    at = utc_instant(now)
    with transaction(conn):
        plan_id = week_plans.next_id(conn, week)
        week_plans.approve(
            conn,
            {
                "id": plan_id,
                "week": week,
                "position": draft.position.week,
                "approved_at": at,
                "write_plan_hash": found.write_plan_hash,
                "draft_hash": draft_hash(data),
                "recorded_at": at,
            },
            supersedes=draft.supersedes,
            overrides=[_override_row(o) for o in draft.overrides],
            prescriptions=_prescription_rows(found.checked, units),
            acknowledgements=[_acknowledgement_row(a) for a in found.acknowledgements],
        )
    return plan_id


def _override_row(override: PlanOverride) -> dict[str, object]:
    return {
        "kind": override.kind,
        "session_id": override.session_id,
        "exercise_id": override.exercise_id,
        "date": None if override.date is None else override.date.isoformat(),
        "params": _json(override_params(override)),
        "because": override.because,
        "text": override.text,
        "evidence": _json(list(override.evidence)) if override.evidence else None,
    }


def _prescription_rows(checked: CheckedPlan, units: Units) -> list[dict[str, object]]:
    """Each line frozen with its place in the whole plan, its steps and every flag of the plan
    that bears on it."""
    lines = (
        (prescribed, line) for prescribed in checked.draft.sessions for line in prescribed.lines
    )
    return [
        {
            "session_id": prescribed.session.session_id,
            "date": prescribed.session.date.isoformat(),
            "exercise_id": line.exercise_id,
            "position": position,
            "rung": line.rung,
            "set_groups": _json(frozen_groups(line.groups, units)),
            "derived_from": line.derived_from or "start_load",
            "steps": _json([step.to_json() for step in line.steps]),
            "flags": _json(
                [
                    flag.to_json()
                    for flag in checked.flags
                    if _bears_on(flag, prescribed.session.session_id, line.exercise_id)
                ]
            ),
            "change": line.change,
        }
        for position, (prescribed, line) in enumerate(lines, start=1)
    ]


def _bears_on(flag: Flag, session_id: str, exercise_id: str) -> bool:
    scope = flag.scope
    if scope.kind == "week":
        return True
    if scope.kind == "session":
        return scope.session_id == session_id
    return scope.kind == "line" and (scope.session_id, scope.exercise_id) == (
        session_id,
        exercise_id,
    )


def _acknowledgement_row(acknowledgement: Acknowledgement) -> dict[str, object]:
    return {
        "key": str(acknowledgement.key),
        "params_hash": acknowledgement.params_hash,
        "because": acknowledgement.because,
        "text": acknowledgement.text,
        "evidence": _json(list(acknowledgement.evidence)) if acknowledgement.evidence else None,
    }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
