import datetime

from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import a_squat_program, squat_logged
from support.programs import a_config

from coach.services.hevy_import import import_hevy
from coach.services.plan_apply import apply, dry_run
from coach.store import mirrors, routine_map
from coach.store.connection import Connection

LATER = FixedClock(datetime.datetime(2026, 10, 31, 9, 0, tzinfo=datetime.UTC))
PIN_115 = """
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Hold the squat under the last top set."
"""


def push(conn: Connection, hevy: FakeHevy, data: bytes) -> None:
    config, kits = a_config(hevy=True), (kit_files(),)
    digest = dry_run(
        conn, data, file="p.toml", config=config, kits=kits, clock=FixedClock()
    ).write_plan_hash
    apply(
        conn,
        hevy,
        data,
        file="p.toml",
        expect=digest,
        config=config,
        kits=kits,
        clock=FixedClock(),
    )


def a_pushed_week() -> tuple[Connection, FakeHevy, str]:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    hevy = FakeHevy(FixedClock())
    push(conn, hevy, a_plan_draft(conn, hevy=True))
    return conn, hevy, routine_map.mapped(conn)["lower"]


def drift_keys(conn: Connection, hevy: FakeHevy) -> list[tuple[str, object]]:
    found = import_hevy(conn, hevy, LATER, full=False, units="lb").warnings
    return [(f.key, f.params["drift_class"]) for f in found if f.code == "routine_drift"]


def test_an_app_edit_to_a_live_routine_warns_routine_drift_until_the_next_push_overwrites_it() -> (
    None
):
    conn, hevy, routine = a_pushed_week()
    quiet = drift_keys(conn, hevy)
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")

    drifted = drift_keys(conn, hevy)
    push(conn, hevy, a_plan_draft(conn, hevy=True, overrides=PIN_115))

    assert quiet == []
    assert drifted == [(f"routine_drift@routine:{routine}", "load")]
    assert drift_keys(conn, hevy) == []


def test_a_routine_hevy_stops_returning_flips_its_map_row_to_missing_and_keeps_its_mirror_row() -> (
    None
):
    conn, hevy, routine = a_pushed_week()
    hevy.stop_returning(routine)

    import_hevy(conn, hevy, LATER, full=False, units="lb")

    assert routine_map.every(conn) == [("lower", routine, "missing")]
    assert routine in {r.hevy_id for r in mirrors.routines(conn)}
    assert drift_keys(conn, hevy) == []
