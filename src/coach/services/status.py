import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coach.core.check_in import (
    DAY,
    CheckInDue,
    LastCheckIn,
    Window,
    check_in_due,
    check_in_window,
)
from coach.core.clock import Clock
from coach.core.config import DEFAULT_CHECKIN_CADENCE_DAYS, Location, Units
from coach.core.flag import Flag
from coach.core.import_flags import snapshot_stale
from coach.core.instant import utc_instant
from coach.core.kit import KitFiles, TablesState, tables_state
from coach.core.planned_week import RotationPosition, week_monday
from coach.services.cadence import cadence_signals
from coach.services.check_in_warnings import check_in_warnings
from coach.services.closed_weeks import ClosedWeeks, WeekLog
from coach.services.fatigue import Fatigue
from coach.services.hevy_import import standing_warnings
from coach.services.previous_plans import frozen_loads_off_rack
from coach.services.racks import current_racks
from coach.services.rotation import default_week, rotation_position
from coach.store import (
    check_ins,
    decisions,
    follow_ups,
    goals,
    niggles,
    observations,
    phases,
    programs,
    routine_map,
    week_plans,
)
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
    routines_verified: int = 0
    routines_unverified: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlockStatus:
    id: str
    hard_weeks: int
    ceiling: int | None
    light_week_pending: bool = False


@dataclass(frozen=True)
class WeekPosition:
    week: datetime.date
    position: RotationPosition


@dataclass(frozen=True)
class StatusResult:
    engine_version: str
    pin: str
    hevy_on: bool
    store_schema_version: int
    last_import: str | None
    last_import_age_days: int | None
    workouts: dict[str, int]
    kit: tuple[KitTables, ...]
    export: ExportState
    program: ProgramInForce | None
    goal: CurrentGoal | None
    phase: OpenPhase | None
    check_in: CheckInDue
    niggles: tuple[str, ...]
    follow_ups_due: tuple[str, ...]
    decisions: dict[str, tuple[str, ...]]
    observations: tuple[str, ...]
    warnings: tuple[Flag, ...]
    plan: PlanInForce | None = None
    rotation: WeekPosition | None = None
    block: BlockStatus | None = None


def status(
    conn: Connection,
    clock: Clock,
    *,
    engine_version: str,
    pin: str,
    hevy_on: bool,
    exported: Mapping[str, str],
    units: Units,
    bodyweight_units: Units | None = None,
    locations: Sequence[Location] = (),
    kits: Sequence[KitFiles] = (),
    cadence_days: int = DEFAULT_CHECKIN_CADENCE_DAYS,
) -> StatusResult:
    """`exported` is the export as it stands on disk, file name to text; `bodyweight_units`
    defaults to the lift units."""
    now = clock.now()
    today = clock.today()
    open_niggles = [n for n in niggles.every(conn) if n["status"] != "resolved"]
    last = last_import_at(conn)
    stale = snapshot_stale(last, now) if hevy_on else None
    monday = week_monday(today)
    log = WeekLog(conn, units)
    fatigue = Fatigue(conn, log)
    pending = fatigue.standing() is not None
    closed = log.closed_by(check_ins.current_windows(conn))
    return StatusResult(
        engine_version=engine_version,
        pin=pin,
        hevy_on=hevy_on,
        store_schema_version=schema_version(conn),
        last_import=utc_instant(last) if last else None,
        last_import_age_days=(now - last).days if last else None,
        workouts=counts_by_source(conn),
        kit=tuple(KitTables(files.location, files.kit, tables_state(files)) for files in kits),
        export=_export_state(conn, engine_version, exported),
        program=_program(conn),
        goal=_current_goal(conn),
        phase=phases.open_phase(conn),
        check_in=_check_in_due(conn, fatigue, today, cadence_days),
        niggles=tuple(str(n["id"]) for n in open_niggles),
        follow_ups_due=_follow_ups_due(conn, today),
        decisions=_decisions_in_force(conn, today),
        observations=tuple(observations.current(conn)),
        warnings=(
            *((stale,) if stale else ()),
            *standing_warnings(conn, units),
            *frozen_loads_off_rack(
                conn,
                current_racks(locations, kits, units),
                monday=default_week(conn, today),
            ),
            *check_in_warnings(
                conn,
                log,
                _open_window(conn, today),
                on=today,
                bodyweight_units=bodyweight_units or units,
            ),
            *cadence_signals(conn, closed, units=units, on=today),
        ),
        plan=_plan_in_force(conn, monday),
        rotation=_rotation(conn, monday),
        block=_block(conn, closed, pending),
    )


def _open_window(conn: Connection, today: datetime.date) -> Window:
    """The days the next check-in would review, up to today; it starts after today when a
    check-in recorded today already reviewed them."""
    previous = check_ins.newest_current(conn)
    if previous is not None:
        return Window(previous.window.end + DAY, today)
    return check_in_window(today, first_plan_monday=week_plans.first_week(conn))


def _check_in_due(
    conn: Connection, fatigue: Fatigue, today: datetime.date, cadence_days: int
) -> CheckInDue:
    due = check_in_due_on(conn, today, cadence_days)
    if due.window is None or fatigue.opened_on(due.window, today).proposal.state != "propose":
        return due
    return check_in_due_on(conn, today, cadence_days, light_week_proposed=True)


def check_in_due_on(
    conn: Connection,
    today: datetime.date,
    cadence_days: int,
    *,
    light_week_proposed: bool = False,
) -> CheckInDue:
    last = check_ins.newest_current(conn)
    last_deep = check_ins.last_deep(conn)
    redesigned = programs.block_opened(conn)
    deferrals = [
        str(d["until"])
        for d in decisions.in_force(conn, today.isoformat())
        if d["kind"] == "defer_deep_review"
    ]
    return check_in_due(
        today,
        cadence_days=cadence_days,
        last=LastCheckIn(last.date, last.tier, last.window) if last else None,
        last_deep=last_deep,
        first_plan_monday=week_plans.first_week(conn),
        redesign_since_deep=bool(
            last_deep and redesigned and datetime.date.fromisoformat(redesigned) > last_deep
        ),
        light_week_proposed=light_week_proposed,
        deep_deferred_until=datetime.date.fromisoformat(max(deferrals)) if deferrals else None,
    )


def _follow_ups_due(conn: Connection, today: datetime.date) -> tuple[str, ...]:
    return tuple(
        str(f["id"])
        for f in follow_ups.every(conn)
        if f["kind"] in ("kept", "deferred") and str(f["due"]) <= today.isoformat()
    )


def _decisions_in_force(conn: Connection, today: datetime.date) -> dict[str, tuple[str, ...]]:
    by_kind: dict[str, list[str]] = {}
    for decision in decisions.in_force(conn, today.isoformat()):
        by_kind.setdefault(str(decision["kind"]), []).append(str(decision["id"]))
    return {kind: tuple(ids) for kind, ids in sorted(by_kind.items())}


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
    plan_id = str(row["id"])
    live = routine_map.live(conn)
    projected = {str(r["session_id"]) for r in week_plans.prescriptions(conn, plan_id)}
    verified = [
        m
        for m in live
        if m.status == "active" and (m.plan_id == plan_id or m.session_id not in projected)
    ]
    return PlanInForce(
        plan_id,
        str(row["week"]),
        str(row["approved_at"]),
        str(row["write_plan_hash"]),
        routines_verified=len(verified),
        routines_unverified=tuple(m.session_id for m in live if m not in verified),
    )


def _block(conn: Connection, closed: ClosedWeeks, pending: bool) -> BlockStatus | None:
    version = programs.latest(conn)
    if version is None:
        return None
    block = closed.open_block
    if block is None:
        return None
    deload = version.form.deload
    ceiling = deload.hard_weeks_ceiling if deload else None
    return BlockStatus(block.id, block.hard_weeks, ceiling, pending)


def _rotation(conn: Connection, monday: datetime.date) -> WeekPosition | None:
    version = programs.latest(conn)
    if version is None:
        return None
    return WeekPosition(monday, rotation_position(conn, version, monday))
