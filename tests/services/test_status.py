from collections.abc import Mapping

from support.scenarios import a_session

from coach.core.kit import KitFiles
from coach.services.publish import publish
from coach.services.status import ExportState, KitTables, StatusResult, status
from coach.store.connection import Connection, open_store

ENGINE = "0.4.0"


def status_of(conn: Connection, exported: Mapping[str, str]) -> StatusResult:
    return status(conn, engine_version=ENGINE, pin=ENGINE, hevy_on=True, exported=exported)


def published(conn: Connection) -> dict[str, str]:
    return dict(publish(conn, engine_version=ENGINE).files)


def test_status_reports_the_engine_against_its_pin_and_the_schema_version() -> None:
    conn = open_store(":memory:")

    result = status_of(conn, published(conn))

    assert result == StatusResult(
        engine_version=ENGINE,
        pin=ENGINE,
        hevy_on=True,
        schema_version=1,
        kit=(),
        export=ExportState(behind_store=False, store_behind_export=False),
    )


def test_status_reports_each_plate_pool_locations_kit_tables_current_or_stale() -> None:
    conn = open_store(":memory:")
    home = KitFiles("home", "home", {"inventory_sha256": "abc"}, "abc")
    cabin = KitFiles("cabin", "travel", {"inventory_sha256": "abc"}, "def")

    result = status(
        conn,
        engine_version=ENGINE,
        pin=ENGINE,
        hevy_on=False,
        exported={},
        kits=(home, cabin),
    )

    assert result.kit == (
        KitTables(location="home", kit="home", tables="current"),
        KitTables(location="cabin", kit="travel", tables="stale"),
    )


def test_with_no_export_yet_the_export_is_behind_the_store() -> None:
    result = status_of(open_store(":memory:"), {})

    assert result.export == ExportState(behind_store=True, store_behind_export=False)


def test_a_row_written_after_publish_puts_the_export_behind_the_store() -> None:
    conn = open_store(":memory:")
    exported = published(conn)
    a_session(conn, "push_a")

    result = status_of(conn, exported)

    assert result.export == ExportState(behind_store=True, store_behind_export=False)


def test_a_manifest_with_more_rows_than_the_store_puts_the_store_behind_the_export() -> None:
    elsewhere = open_store(":memory:")
    a_session(elsewhere, "push_a")

    result = status_of(open_store(":memory:"), published(elsewhere))

    assert result.export.store_behind_export is True
