from support.clock import FixedClock
from support.closed_weeks import a_hard_squat_week, closed_through, monday
from support.plans import a_squat_program
from support.programs import the_worked_store

from coach.services.status import BlockStatus, status
from coach.store.connection import Connection


def block_of(conn: Connection) -> BlockStatus | None:
    result = status(
        conn,
        FixedClock(),
        engine_version="0.4.0",
        pin="0.4.0",
        hevy_on=False,
        exported={},
        units="lb",
    )
    return result.block


def test_status_shows_the_open_blocks_hard_weeks_against_the_ceiling() -> None:
    conn = a_squat_program()
    for n in range(2):
        a_hard_squat_week(conn, monday(n))
    closed_through(conn, 2)

    assert block_of(conn) == BlockStatus("b-2026-10-30", 2, 6)


def test_with_no_program_there_is_no_block() -> None:
    assert block_of(the_worked_store()) is None
