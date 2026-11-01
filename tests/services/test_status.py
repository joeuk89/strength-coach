import datetime
from collections.abc import Mapping

from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.goals import STRENGTH, WORKED, with_phase
from support.hevy_payloads import a_workout
from support.kit_fixtures import kit_files
from support.plans import a_squat_program, an_approved_plan
from support.program_drafts import a_draft, toml
from support.programs import a_config, the_worked_store
from support.scenarios import a_session

from coach.core.clock import Clock
from coach.core.goal import Until
from coach.core.kit import KitFiles
from coach.core.planned_week import RotationPosition
from coach.services.goal_adopt import goal_adopt
from coach.services.hevy_import import import_hevy
from coach.services.program import adopt
from coach.services.publish import publish
from coach.services.status import (
    CurrentGoal,
    ExportState,
    KitTables,
    PlanInForce,
    ProgramInForce,
    StatusResult,
    WeekPosition,
    status,
)
from coach.store.catalogue import seed_catalogue
from coach.store.connection import Connection, open_store
from coach.store.phases import OpenPhase

ENGINE = "0.4.0"
A = "10000000-0000-4000-8000-00000000000a"
B = "10000000-0000-4000-8000-00000000000b"


def status_of(
    conn: Connection,
    exported: Mapping[str, str] | None = None,
    clock: Clock | None = None,
    *,
    hevy_on: bool = True,
) -> StatusResult:
    return status(
        conn,
        clock or FixedClock(),
        engine_version=ENGINE,
        pin=ENGINE,
        hevy_on=hevy_on,
        exported={} if exported is None else exported,
    )


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
        last_import=None,
        last_import_age_days=None,
        workouts={"hevy": 0, "manual": 0},
        kit=(),
        export=ExportState(behind_store=False, store_behind_export=False),
        program=None,
        goal=None,
        phase=None,
        warnings=(),
        plan=None,
        rotation=None,
    )


def test_status_reports_the_age_of_the_last_import_and_the_workouts_read() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(
        conn, FakeHevy(clock, workouts=[a_workout(A), a_workout(B)]), clock, full=True, units="kg"
    )
    import_hevy(conn, FakeHevy(clock, workouts=[a_workout(B)]), clock, full=True, units="kg")
    later = FixedClock(clock.moment + datetime.timedelta(days=3, hours=2))

    result = status_of(conn, clock=later)

    assert (result.last_import, result.last_import_age_days) == ("2026-10-30T12:00:00Z", 3)
    assert result.workouts == {"hevy": 1, "manual": 0}
    assert result.warnings == ()


def test_status_warns_snapshot_stale_past_seven_days_while_hevy_is_on() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(conn, FakeHevy(clock), clock, full=True, units="kg")
    later = FixedClock(clock.moment + datetime.timedelta(days=8))

    on = status_of(conn, clock=later)
    off = status_of(conn, clock=later, hevy_on=False)

    assert [w.key for w in on.warnings] == ["snapshot_stale@instance"]
    assert off.warnings == ()


def test_status_reports_each_plate_pool_locations_kit_tables_current_or_stale() -> None:
    conn = open_store(":memory:")
    home = KitFiles("home", "home", {"inventory_sha256": "abc"}, "abc")
    cabin = KitFiles("cabin", "travel", {"inventory_sha256": "abc"}, "def")

    result = status(
        conn,
        FixedClock(),
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


def adopted(*drafts: str) -> StatusResult:
    conn = open_store(":memory:")
    with conn:
        seed_catalogue(conn)
    for draft in drafts:
        goal_adopt(conn, draft.encode("utf-8"), file="g.toml", clock=FixedClock())
    return status_of(conn, hevy_on=False)


def test_status_shows_the_current_goal_and_the_open_phase() -> None:
    result = adopted(WORKED)

    assert result.goal == CurrentGoal("g-0001", "hypertrophy", ("bb_bench_press", "pull_up"))
    assert result.phase == OpenPhase("ph-0001", "maintenance", Until("coachs_call"))


def test_status_shows_the_newest_goal_and_the_phase_opened_after_a_close() -> None:
    result = adopted(
        WORKED,
        with_phase(
            STRENGTH,
            'close = { because = "done" }\n'
            'open = { kind = "deficit", until = { kind = "bodyweight_at_or_below", value = 78.5 }, '
            'because = "cut" }',
        ),
    )

    assert result.goal == CurrentGoal("g-0002", "strength", ("bb_bench_press",))
    assert result.phase == OpenPhase("ph-0002", "deficit", Until("bodyweight_at_or_below", 78.5))


def test_status_shows_no_phase_once_it_is_closed() -> None:
    result = adopted(WORKED, with_phase(STRENGTH, 'close = { because = "done" }'))

    assert result.phase is None


def test_status_reports_the_program_version_in_force() -> None:
    conn = the_worked_store()
    assert status_of(conn, hevy_on=False).program is None
    adopt(
        conn,
        toml(a_draft()),
        file="d.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )

    result = status_of(conn, hevy_on=False)

    assert result.program == ProgramInForce("pv-1", "redesign", "hypertrophy", "2026-10-30")


def test_status_shows_no_plan_in_force_and_the_rotation_position_for_this_week() -> None:
    conn = a_squat_program(
        schedule={"rotation": ["A", "B"], "A": {"mon": "lower"}, "B": {"wed": "lower"}}
    )

    before = status_of(conn, hevy_on=False)

    assert before.plan is None
    assert before.rotation == WeekPosition(
        datetime.date(2026, 10, 26), RotationPosition("A", "program_adopt")
    )


def test_status_shows_the_plan_in_force_this_week() -> None:
    conn = a_squat_program()
    an_approved_plan(conn, "2026-10-26", approved_at="2026-10-25T18:00:00+00:00")

    result = status_of(conn, hevy_on=False)

    assert result.plan == PlanInForce(
        "wp-2026-10-26", "2026-10-26", "2026-10-25T18:00:00+00:00", "sha256:w"
    )
    assert result.rotation == WeekPosition(
        datetime.date(2026, 10, 26), RotationPosition("A", "plan_in_force")
    )
