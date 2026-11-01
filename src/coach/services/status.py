import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coach.core.clock import Clock
from coach.core.flag import Flag
from coach.core.import_flags import snapshot_stale
from coach.core.instant import utc_instant
from coach.core.kit import KitFiles, TablesState, tables_state
from coach.core.planned_week import RotationPosition, week_monday
from coach.services.rotation import rotation_position
from coach.store import goals, phases, programs, week_plans
from coach.store.connection import Connection, schema_version
from coach.store.export import MANIFEST, export, parse_manifest, tables_behind
from coach.store.import_runs import last_import_at
from coach.store.phases import OpenPhase
from coach.store.workouts import counts_by_source


@dataclass(frozen=True)
class ExportState:
    behind_store: bool
    store_behind_export: bool


@dataclass(frozen=True)
class KitTables:
    location: str
    kit: str
    tables: TablesState


@dataclass(frozen=True)
class ProgramInForce:
    version: str
    kind: str
    emphasis: str
    adopted: str


@dataclass(frozen=True)
class CurrentGoal:
    id: str
    kind: str
    priority_lifts: tuple[str, ...]


@dataclass(frozen=True)
class PlanInForce:
    id: str
    week: str
    approved_at: str
    write_plan_hash: str


@dataclass(frozen=True)
class WeekPosition:
    week: datetime.date
    position: RotationPosition


@dataclass(frozen=True)
class StatusResult:
    engine_version: str
    pin: str
    hevy_on: bool
    schema_version: int
    last_import: str | None
    last_import_age_days: int | None
    workouts: dict[str, int]
    kit: tuple[KitTables, ...]
    export: ExportState
    program: ProgramInForce | None
    goal: CurrentGoal | None
    phase: OpenPhase | None
    warnings: tuple[Flag, ...]
    plan: PlanInForce | None = None
    rotation: WeekPosition | None = None


def status(
    conn: Connection,
    clock: Clock,
    *,
    engine_version: str,
    pin: str,
    hevy_on: bool,
    exported: Mapping[str, str],
    kits: Sequence[KitFiles] = (),
) -> StatusResult:
    """`exported` is the export as it stands on disk, file name to text."""
    now = clock.now()
    last = last_import_at(conn)
    stale = snapshot_stale(last, now) if hevy_on else None
    monday = week_monday(clock.today())
    return StatusResult(
        engine_version=engine_version,
        pin=pin,
        hevy_on=hevy_on,
        schema_version=schema_version(conn),
        last_import=utc_instant(last) if last else None,
        last_import_age_days=(now - last).days if last else None,
        workouts=counts_by_source(conn),
        kit=tuple(KitTables(files.location, files.kit, tables_state(files)) for files in kits),
        export=_export_state(conn, engine_version, exported),
        program=_program(conn),
        goal=_current_goal(conn),
        phase=phases.open_phase(conn),
        warnings=(stale,) if stale else (),
        plan=_plan_in_force(conn, monday),
        rotation=_rotation(conn, monday),
    )


def _export_state(
    conn: Connection, engine_version: str, exported: Mapping[str, str]
) -> ExportState:
    manifest = parse_manifest(exported[MANIFEST]) if MANIFEST in exported else None
    return ExportState(
        behind_store=export(conn, engine_version).files != exported,
        store_behind_export=manifest is not None and bool(tables_behind(conn, manifest)),
    )


def _current_goal(conn: Connection) -> CurrentGoal | None:
    goal_id = goals.current_id(conn)
    stored = goals.get(conn, goal_id) if goal_id else None
    if stored is None:
        return None
    return CurrentGoal(stored.id, stored.goal.kind, stored.goal.priority_lifts)


def _program(conn: Connection) -> ProgramInForce | None:
    version = programs.latest(conn)
    if version is None:
        return None
    form = version.form
    return ProgramInForce(version.id, form.kind, form.emphasis, version.adopted)


def _plan_in_force(conn: Connection, monday: datetime.date) -> PlanInForce | None:
    row = week_plans.in_force(conn, monday.isoformat())
    if row is None:
        return None
    return PlanInForce(
        str(row["id"]), str(row["week"]), str(row["approved_at"]), str(row["write_plan_hash"])
    )


def _rotation(conn: Connection, monday: datetime.date) -> WeekPosition | None:
    version = programs.latest(conn)
    if version is None:
        return None
    return WeekPosition(monday, rotation_position(conn, version, monday))
