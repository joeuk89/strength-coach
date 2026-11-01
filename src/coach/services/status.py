from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coach.core.clock import Clock
from coach.core.flag import Flag
from coach.core.import_flags import snapshot_stale
from coach.core.instant import utc_instant
from coach.core.kit import KitFiles, TablesState, tables_state
from coach.store.connection import Connection, schema_version
from coach.store.export import MANIFEST, export, parse_manifest, tables_behind
from coach.store.import_runs import last_import_at
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
    warnings: tuple[Flag, ...]


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
        warnings=(stale,) if stale else (),
    )


def _export_state(
    conn: Connection, engine_version: str, exported: Mapping[str, str]
) -> ExportState:
    manifest = parse_manifest(exported[MANIFEST]) if MANIFEST in exported else None
    return ExportState(
        behind_store=export(conn, engine_version).files != exported,
        store_behind_export=manifest is not None and bool(tables_behind(conn, manifest)),
    )
