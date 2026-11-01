"""One scenario per warning outside a plan: a store seeded into the code's state, `status` read
while it stands, then the fact behind it changed by its own verb and `status` read again."""

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from coach.core.config import Location
from coach.core.kit import KitFiles
from coach.services.record import record
from coach.services.status import status
from coach.store.connection import Connection
from support.clock import FixedClock, at
from support.ledger import a_store

ENGINE = "0.4.0"
TODAY = datetime.date(2026, 11, 29)


@dataclass(frozen=True)
class Standing:
    raised: tuple[str, ...]
    cleared: tuple[str, ...]


type Scenario = Callable[[Path, pytest.MonkeyPatch], Standing]


def status_codes(
    conn: Connection,
    on: datetime.date = TODAY,
    *,
    hevy_on: bool = False,
    locations: tuple[Location, ...] = (),
    kits: tuple[KitFiles, ...] = (),
) -> tuple[str, ...]:
    """Lift loads in lb and bodyweight in kg, so a scenario catches either read in the other's."""
    result = status(
        conn,
        FixedClock(at(on)),
        engine_version=ENGINE,
        pin=ENGINE,
        hevy_on=hevy_on,
        exported={},
        units="lb",
        bodyweight_units="kg",
        locations=locations,
        kits=kits,
    )
    return tuple(w.code for w in result.warnings)


def recorded(conn: Connection, text: str) -> None:
    record(conn, text.encode(), file="d.toml", clock=FixedClock())


def followup_due(_: Path, __: pytest.MonkeyPatch) -> Standing:
    conn = a_store()
    recorded(conn, '[[followup]]\nraised = 2026-11-01\ntext = "retest"\ndue = 2026-11-28\n')
    raised = status_codes(conn)
    recorded(conn, '[[followup]]\nfollowup = "f-0001"\nkind = "resolved"\ndate = 2026-11-29\n')
    return Standing(raised, status_codes(conn))


SCENARIOS: dict[str, Scenario] = {
    "followup_due": followup_due,
}
