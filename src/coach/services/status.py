from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coach.core.kit import KitFiles, TablesState, tables_state
from coach.store.connection import Connection, schema_version
from coach.store.export import MANIFEST, export, parse_manifest, tables_behind


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
    kit: tuple[KitTables, ...]
    export: ExportState


def status(
    conn: Connection,
    *,
    engine_version: str,
    pin: str,
    hevy_on: bool,
    exported: Mapping[str, str],
    kits: Sequence[KitFiles] = (),
) -> StatusResult:
    """`exported` is the export as it stands on disk, file name to text."""
    return StatusResult(
        engine_version=engine_version,
        pin=pin,
        hevy_on=hevy_on,
        schema_version=schema_version(conn),
        kit=tuple(KitTables(files.location, files.kit, tables_state(files)) for files in kits),
        export=_export_state(conn, engine_version, exported),
    )


def _export_state(
    conn: Connection, engine_version: str, exported: Mapping[str, str]
) -> ExportState:
    manifest = parse_manifest(exported[MANIFEST]) if MANIFEST in exported else None
    return ExportState(
        behind_store=export(conn, engine_version).files != exported,
        store_behind_export=manifest is not None and bool(tables_behind(conn, manifest)),
    )
