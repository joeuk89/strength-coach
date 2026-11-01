from collections.abc import Sequence
from dataclasses import dataclass

from coach.core.kit import KitFiles, TablesState, tables_state
from coach.store.connection import Connection, schema_version


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


def status(
    conn: Connection,
    *,
    engine_version: str,
    pin: str,
    hevy_on: bool,
    kits: Sequence[KitFiles] = (),
) -> StatusResult:
    return StatusResult(
        engine_version=engine_version,
        pin=pin,
        hevy_on=hevy_on,
        schema_version=schema_version(conn),
        kit=tuple(KitTables(files.location, files.kit, tables_state(files)) for files in kits),
    )
