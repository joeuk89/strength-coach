import datetime

from support.clock import FixedClock
from support.closed_weeks import a_hard_squat_week, a_planned_squat_week, closed_through, monday
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_draft, a_session, toml
from support.programs import a_config

from coach.services.program import AdoptResult, adopt
from coach.store.connection import Connection

SUNDAY_AFTER = FixedClock(datetime.datetime(2026, 11, 29, 12, tzinfo=datetime.UTC))


def three_of_four_weeks_trained() -> Connection:
    """Four ordinary closed weeks of one core session, the third a Miss with the squat trained
    off-plan on the Wednesday, so no layoff makes it a return week: 75 %."""
    conn = a_squat_program()
    for n in (0, 1, 3):
        a_hard_squat_week(conn, monday(n))
    a_planned_squat_week(conn, monday(2))
    squat_logged(conn, "h-off", "2026-11-18", (120, 8, 8))
    closed_through(conn, 4)
    return conn


def adopted(conn: Connection, *sessions: dict[str, object], kind: str = "amend") -> AdoptResult:
    draft = a_draft(*sessions, kind=kind, because="add an upper day")
    return adopt(
        conn,
        toml(draft),
        file="v2.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=SUNDAY_AFTER,
        dry_run=True,
    )


def test_a_version_adding_a_core_session_under_watch_adherence_warns() -> None:
    conn = three_of_four_weeks_trained()

    result = adopted(conn, a_session("lower", SQUAT_LINE), a_session("upper"))

    [flag] = [f for f in result.warnings if f.code == "core_session_added_low_adherence"]
    assert flag.key == "core_session_added_low_adherence@session:upper"
    assert flag.params == {"session_id": "upper", "adherence": 0.75, "weeks": 4}


def test_keeping_the_same_core_sessions_raises_no_adherence_warning() -> None:
    result = adopted(three_of_four_weeks_trained(), a_session("lower", SQUAT_LINE))

    assert "core_session_added_low_adherence" not in [f.code for f in result.warnings]


def test_a_redesign_reports_the_derived_open_block_and_its_hard_weeks() -> None:
    result = adopted(three_of_four_weeks_trained(), a_session("lower", SQUAT_LINE), kind="redesign")

    [flag] = [f for f in result.warnings if f.code == "block_open_at_redesign"]
    assert flag.params == {"block_id": "b-2026-11-23", "hard_weeks": 1}


def test_an_amend_keeps_the_derived_open_block() -> None:
    result = adopted(three_of_four_weeks_trained(), a_session("lower", SQUAT_LINE))

    assert (result.block, result.block_reset) == ("b-2026-11-23", False)
