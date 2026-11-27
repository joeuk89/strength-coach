import datetime

from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import a_squat_program, squat_logged
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config

from coach.services.plan_apply import apply, dry_run
from coach.services.program import adopt
from coach.services.status import StatusResult, status
from coach.store.connection import Connection

THIS_MONDAY = datetime.date(2026, 11, 2)
NEXT_MONDAY = datetime.date(2026, 11, 9)
SUNDAY_MORNING = datetime.datetime(2026, 11, 8, 9, 0, tzinfo=datetime.UTC)
SUNDAY_EVENING = datetime.datetime(2026, 11, 8, 18, 0, tzinfo=datetime.UTC)
THREE_SETS = a_line(
    "bb_back_squat",
    sets=[
        {"count": 1, "type": "warm_up", "reps": 5},
        {"count": 1, "type": "warm_up", "reps": 3},
        {"count": 3, "reps": [6, 8], "rpe": 8},
    ],
    start_load=100,
)


def a_squat_week() -> Connection:
    conn = a_squat_program(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    return conn


def applied(conn: Connection, hevy: FakeHevy, week: datetime.date, at: datetime.datetime) -> None:
    data = a_plan_draft(conn, hevy=True, week=week)
    config, kits, clock = a_config(hevy=True), (kit_files(),), FixedClock(at)
    digest = dry_run(conn, data, file="p.toml", config=config, kits=kits, clock=clock)
    apply(
        conn,
        hevy,
        data,
        file="p.toml",
        expect=digest.write_plan_hash,
        config=config,
        kits=kits,
        clock=clock,
    )


def an_amend(conn: Connection, at: datetime.datetime) -> None:
    adopt(
        conn,
        toml(
            a_draft(
                a_session("lower", THREE_SETS),
                a_session("upper"),
                kind="amend",
                because="one set fewer",
            )
        ),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(at),
    )


def status_at(conn: Connection, at: datetime.datetime) -> StatusResult:
    return status(
        conn,
        FixedClock(at),
        engine_version="0.3.0",
        pin="0.3.0",
        hevy_on=True,
        exported={},
        units="lb",
    )


def test_after_next_weeks_apply_status_names_this_weeks_plan_and_the_routines_owner() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, THIS_MONDAY, datetime.datetime(2026, 11, 1, 18, 0, tzinfo=datetime.UTC))
    applied(conn, hevy, NEXT_MONDAY, SUNDAY_MORNING)

    shown = status_at(conn, SUNDAY_EVENING).plan

    assert shown is not None
    assert (
        shown.id,
        shown.routines_plan,
        shown.routines_verified,
        shown.routines_unverified,
    ) == ("wp-2026-11-02", "wp-2026-11-09", 2, ())


def test_with_no_next_week_plan_the_routines_are_judged_against_this_weeks_plan() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, THIS_MONDAY, datetime.datetime(2026, 11, 1, 18, 0, tzinfo=datetime.UTC))

    shown = status_at(conn, SUNDAY_EVENING).plan

    assert shown is not None
    assert (shown.routines_plan, shown.routines_verified, shown.routines_unverified) == (
        "wp-2026-11-02",
        2,
        (),
    )


def behind(result: StatusResult) -> list[str]:
    return [w.key for w in result.warnings if w.code == "plan_behind_program"]


def test_next_weeks_plan_applied_under_the_new_version_clears_this_weeks_warning() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, THIS_MONDAY, datetime.datetime(2026, 11, 1, 18, 0, tzinfo=datetime.UTC))
    an_amend(conn, datetime.datetime(2026, 11, 4, 12, 0, tzinfo=datetime.UTC))
    assert behind(status_at(conn, SUNDAY_MORNING)) == ["plan_behind_program@week:2026-11-02"]

    applied(conn, hevy, NEXT_MONDAY, SUNDAY_MORNING + datetime.timedelta(hours=1))

    assert behind(status_at(conn, SUNDAY_EVENING)) == []


def test_next_weeks_plan_approved_before_the_amend_leaves_this_weeks_warning() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    applied(conn, hevy, THIS_MONDAY, datetime.datetime(2026, 11, 1, 18, 0, tzinfo=datetime.UTC))
    applied(conn, hevy, NEXT_MONDAY, datetime.datetime(2026, 11, 3, 12, 0, tzinfo=datetime.UTC))
    an_amend(conn, datetime.datetime(2026, 11, 4, 12, 0, tzinfo=datetime.UTC))

    assert behind(status_at(conn, SUNDAY_EVENING)) == ["plan_behind_program@week:2026-11-02"]
