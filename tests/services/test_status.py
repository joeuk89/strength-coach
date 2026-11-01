from coach.services.status import StatusResult, status
from coach.store.connection import open_store


def test_status_reports_the_engine_against_its_pin_and_the_schema_version() -> None:
    conn = open_store(":memory:")

    result = status(conn, engine_version="0.4.0", pin="0.4.0", hevy_on=True)

    assert result == StatusResult(
        engine_version="0.4.0", pin="0.4.0", hevy_on=True, schema_version=1
    )
