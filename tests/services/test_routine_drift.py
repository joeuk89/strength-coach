import datetime
import json

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.ledger import an_exercise
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_draft, a_session, toml
from support.programs import a_config
from support.pushes import a_pushed_week, push

from coach.core.errors import Invalid
from coach.services.hevy_import import import_hevy
from coach.services.program import adopt
from coach.services.record import record
from coach.store import mirrors, routine_map, week_plans
from coach.store.connection import Connection

AT = "2026-10-25T12:00:00+00:00"
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
PIN_125 = PIN_115.replace("load = 115", "load = 125")


def drift_keys(conn: Connection, hevy: FakeHevy) -> list[tuple[str, object]]:
    found = import_hevy(conn, hevy, LATER, full=False, units="lb").warnings
    return [(f.key, f.params["drift_class"]) for f in found if f.code == "routine_drift"]


def drift_plans(conn: Connection, hevy: FakeHevy) -> list[object]:
    found = import_hevy(conn, hevy, LATER, full=False, units="lb").warnings
    return [f.params["plan_in_force"] for f in found if f.code == "routine_drift"]


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


def test_adopting_a_version_that_renames_a_session_raises_no_drift_and_the_rerun_sends_no_put() -> (
    None
):
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    push(conn, hevy, data)
    renamed = a_session("lower", {**SQUAT_LINE, "cues": "Brace hard"}, title="Legs day")
    adopt(
        conn,
        toml(a_draft(renamed)),
        file="next.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=LATER,
    )

    drifted = drift_keys(conn, hevy)
    hevy.calls.clear()
    push(conn, hevy, data)

    assert drifted == []
    assert [c for c in hevy.calls if c[0] == "PUT"] == []


def test_a_routine_left_unchanged_by_a_superseding_plan_is_judged_against_that_plan() -> None:
    conn, hevy, routine = a_pushed_week()
    push(conn, hevy, a_plan_draft(conn, hevy=True, overrides=PIN_125))
    superseding = week_plans.in_force(conn, "2026-11-02")
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")

    found = drift_plans(conn, hevy)

    assert superseding is not None
    assert found == [superseding["id"]]


REHAB = """
[[niggle]]
site = "left shoulder"
date = 2026-10-24
status = "reported"

[niggle.rehab]
session = "shoulder_rehab"
title = "Shoulder rehab"
cadence = "standing"

[[niggle.rehab.line]]
exercise = "dead_hang"
rest_s = 60

[[niggle.rehab.line.sets]]
count = 3
duration_s = 30
"""
RESOLVED = '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-29\nstatus = "resolved"\n'


def test_a_retired_rehab_routine_whose_read_back_differed_raises_no_drift_on_import() -> None:
    conn = a_squat_program()
    an_exercise(
        conn,
        "dead_hang",
        load_mode="duration",
        equipment_kind="bodyweight",
        hevy_template_id="DH-0001",
    )
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    record(conn, REHAB.encode(), file="n.toml", clock=FixedClock())
    hevy = FakeHevy(FixedClock())
    push(conn, hevy, a_plan_draft(conn, hevy=True))
    rehab = routine_map.mapped(conn)["shoulder_rehab"]
    record(conn, RESOLVED.encode(), file="r.toml", clock=FixedClock())
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, a_plan_draft(conn, hevy=True))

    held = routine_map.every(conn)

    assert ("shoulder_rehab", rehab, "unverified") in held
    assert drift_keys(conn, hevy) == []


def test_a_shared_program_folder_title_skips_drift_rather_than_failing_the_pull() -> None:
    """Two Hevy folders titled Program mirror neither; `plan apply` refuses that state."""
    conn, hevy, routine = a_pushed_week()
    hevy.edit_in_app(routine, 70.0, "2026-10-31T08:00:00Z")
    with conn:
        conn.execute("DELETE FROM folder")
    shared = [
        {"id": 7000 + n, "index": n, "title": "Program", "updated_at": AT, "created_at": AT}
        for n in range(2)
    ]
    held = [json.loads(r.raw) for r in hevy.routines()]

    assert drift_keys(conn, FakeHevy(LATER, routines=held, folders=shared)) == []
    assert mirrors.folders(conn) == ()
