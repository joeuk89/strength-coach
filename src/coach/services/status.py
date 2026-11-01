from dataclasses import dataclass

from coach.store.connection import Connection, schema_version


@dataclass(frozen=True)
class StatusResult:
    engine_version: str
    pin: str
    schema_version: int


def status(conn: Connection, *, engine_version: str, pin: str) -> StatusResult:
    return StatusResult(engine_version=engine_version, pin=pin, schema_version=schema_version(conn))
