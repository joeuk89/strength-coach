from dataclasses import dataclass

from coach.store.connection import Connection, schema_version


@dataclass(frozen=True)
class StatusResult:
    engine_version: str
    pin: str
    hevy_on: bool
    schema_version: int


def status(conn: Connection, *, engine_version: str, pin: str, hevy_on: bool) -> StatusResult:
    return StatusResult(
        engine_version=engine_version,
        pin=pin,
        hevy_on=hevy_on,
        schema_version=schema_version(conn),
    )
