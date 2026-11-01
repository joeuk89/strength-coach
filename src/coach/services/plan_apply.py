"""`plan apply --dry-run`: the one plan check, the Hevy actions and the Write plan hash, offline
and read-only (ADR 0006; docs/spec/verbs.md, "Not leaves")."""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from coach.core.clock import Clock
from coach.core.config import Config
from coach.core.errors import Invalid
from coach.core.flag import Acknowledgement, Flag, FlagKey
from coach.core.hevy_actions import HevyActions, MappedRoutine, hevy_actions
from coach.core.kit import KitFiles
from coach.core.plan_check import CheckedPlan, TemplateFacts, check_plan
from coach.core.plan_input import parse_plan_input
from coach.core.program.checks import TEMPLATE_COLUMNS
from coach.core.registries.ledger import Reason
from coach.core.write_plan import write_plan_hash
from coach.services.plan_draft import plan_draft
from coach.store import decisions, exercises, mirrors, niggles, programs, routine_map
from coach.store.connection import Connection


@dataclass(frozen=True)
class CheckedDraft:
    checked: CheckedPlan
    acknowledgements: tuple[Acknowledgement, ...]


@dataclass(frozen=True)
class DryRun:
    checked: CheckedPlan
    actions: HevyActions
    write_plan_hash: str

    @property
    def flags(self) -> tuple[Flag, ...]:
        return self.checked.flags


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
    drafted = plan_draft(
        conn,
        config=config,
        kits=kits,
        clock=clock,
        week=found.week,
        overrides=found.overrides,
        position=found.position,
    )
    checked = check_plan(
        drafted.draft,
        acknowledgements=(*found.acknowledgements, *_leave_warning_decisions(conn, found.week)),
        templates=_templates(conn) if config.hevy is not None else None,
    )
    return CheckedDraft(checked, found.acknowledgements)


def dry_run(
    conn: Connection,
    data: bytes,
    *,
    file: str,
    config: Config,
    kits: Sequence[KitFiles],
    clock: Clock,
) -> DryRun:
    validated = validate(conn, data, file=file, config=config, kits=kits, clock=clock)
    checked = validated.checked
    if checked.violations:
        first = checked.violations[0]
        raise Invalid(
            first.code,
            f"the plan has {len(checked.violations)} violation(s); change the fact behind each "
            "and run the dry run again",
            {"flags": [flag.to_summary() for flag in checked.flags]},
        )
    actions = _actions(conn, checked, hevy_on=config.hevy is not None)
    versions = {routine.hevy_id: routine.updated_at for routine in mirrors.routines(conn)}
    digest = write_plan_hash(
        checked.draft,
        acknowledgements=validated.acknowledgements,
        actions=actions,
        routine_versions={r: versions.get(r) for r in actions.touched_routines},
        units=config.athlete.units,
    )
    return DryRun(checked, actions, digest)


def _actions(conn: Connection, checked: CheckedPlan, *, hevy_on: bool) -> HevyActions:
    if not hevy_on:
        return HevyActions()
    version = programs.latest(conn)
    assert version is not None
    in_force = {s.id for s in (*version.form.sessions, *niggles.open_rehab_sessions(conn))}
    return hevy_actions(
        checked.draft.sessions,
        routine_map=[
            MappedRoutine(session, routine, status)
            for session, routine, status in routine_map.every(conn)
        ],
        folders={folder.role for folder in mirrors.folders(conn)},
        sessions_in_force=in_force,
        templates=_templates(conn),
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


def _leave_warning_decisions(conn: Connection, week: datetime.date) -> tuple[Acknowledgement, ...]:
    """`leave_warning` Decisions in force on the week's Monday (validation.md, "Longer than a
    week")."""
    return tuple(
        Acknowledgement(
            FlagKey.parse(str(params["flag"])),
            str(params["params_hash"]),
            cast(Reason, row["because"]),
            str(row["text"]),
            tuple(str(ref) for ref in cast(list[object], row["evidence"])),
            source="decision",
        )
        for row in decisions.in_force(conn, week.isoformat())
        if row["kind"] == "leave_warning"
        for params in (cast(dict[str, object], row["params"]),)
    )
