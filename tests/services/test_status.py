from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.program_drafts import a_draft, toml
from support.programs import a_config, the_worked_store

from coach.core.kit import KitFiles
from coach.services.program import adopt
from coach.services.status import KitTables, ProgramInForce, StatusResult, status
from coach.store.connection import open_store


def test_status_reports_the_engine_against_its_pin_and_the_schema_version() -> None:
    conn = open_store(":memory:")

    result = status(conn, engine_version="0.4.0", pin="0.4.0", hevy_on=True)

    assert result == StatusResult(
        engine_version="0.4.0", pin="0.4.0", hevy_on=True, schema_version=1, kit=()
    )


def test_status_reports_each_plate_pool_locations_kit_tables_current_or_stale() -> None:
    conn = open_store(":memory:")
    home = KitFiles("home", "home", {"inventory_sha256": "abc"}, "abc")
    cabin = KitFiles("cabin", "travel", {"inventory_sha256": "abc"}, "def")

    result = status(conn, engine_version="0.4.0", pin="0.4.0", hevy_on=False, kits=(home, cabin))

    assert result.kit == (
        KitTables(location="home", kit="home", tables="current"),
        KitTables(location="cabin", kit="travel", tables="stale"),
    )


def test_status_reports_the_program_version_in_force() -> None:
    conn = the_worked_store()
    assert status(conn, engine_version="0.4.0", pin="0.4.0", hevy_on=False).program is None
    adopt(
        conn,
        toml(a_draft()),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    result = status(conn, engine_version="0.4.0", pin="0.4.0", hevy_on=False)

    assert result.program == ProgramInForce("pv-1", "redesign", "hypertrophy", "2026-10-30")
