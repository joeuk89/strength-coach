from collections.abc import Sequence
from dataclasses import dataclass

from coach.core.kit import KitFiles, TablesState, tables_state
from coach.store import programs
from coach.store.connection import Connection, schema_version


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
class StatusResult:
    engine_version: str
    pin: str
    hevy_on: bool
    schema_version: int
    kit: tuple[KitTables, ...]
    program: ProgramInForce | None = None


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
        program=_program(conn),
    )


def _program(conn: Connection) -> ProgramInForce | None:
    version = programs.latest(conn)
    if version is None:
        return None
    form = version.form
    return ProgramInForce(version.id, form.kind, form.emphasis, version.adopted)
