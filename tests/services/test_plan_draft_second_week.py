import datetime
import tomllib

from support.clock import FixedClock
from support.history import a_logged_workout
from support.kit_fixtures import kit_files
from support.plans import (
    SQUAT_TEMPLATE,
    a_frozen_prescription,
    a_plan_override,
    a_squat_program,
    an_approved_plan,
    squat_logged,
)
from support.programs import a_config

from coach.core.flag import Flag
from coach.core.overrides import parse_plan_overrides
from coach.core.units import KG_PER_LB
from coach.services.plan_draft import plan_draft
from coach.services.record import record
from coach.store.connection import Connection

NEXT_MONDAY = datetime.date(2026, 11, 2)
HOLD = """
[[override]]
kind = "hold"
session = "lower"
exercise = "bb_back_squat"
because = "fatigue"
text = "Hold the squat while the knee settles."
"""
# The squat version is adopted at noon on 30 Oct 2026.
AFTER_THE_VERSION = "2026-10-30T13:00:00+00:00"
SQUAT_GROUPS = [{"type": "working", "count": 4, "load": 120.0, "load_kg": 54.43, "range": [6, 8]}]


def flags(conn: Connection, overrides: str = "") -> list[Flag]:
    parsed = parse_plan_overrides(tomllib.loads(overrides), file="plan.toml")
    drafted = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
        week=NEXT_MONDAY,
        overrides=parsed,
    ).draft
    return list(drafted.flags)


def codes(found: list[Flag], code: str) -> list[Flag]:
    return [f for f in found if f.code == code]


def a_held_plan(conn: Connection, week: str) -> str:
    plan_id = an_approved_plan(conn, week)
    a_plan_override(conn, plan_id, "hold", "lower", "bb_back_squat")
    return plan_id


def a_squat_week() -> Connection:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    return conn


def test_the_third_consecutive_plan_with_the_same_hold_raises_override_persisting() -> None:
    conn = a_squat_week()
    a_held_plan(conn, "2026-10-26")
    second = codes(flags(conn, HOLD), "override_persisting")
    a_held_plan(conn, "2026-10-19")

    [third] = codes(flags(conn, HOLD), "override_persisting")

    assert second == []
    assert third.key == "override_persisting@line:2026-11-02/lower/bb_back_squat"
    assert third.params == {
        "kind": "hold",
        "weeks": 3,
        "plan_ids": ["wp-2026-10-19", "wp-2026-10-26"],
    }


def test_a_week_an_override_decision_covered_never_counts() -> None:
    conn = a_squat_week()
    a_held_plan(conn, "2026-10-19")
    a_held_plan(conn, "2026-10-26")
    record(
        conn,
        b'[[decision]]\nkind = "override"\nsession = "lower"\nexercise = "bb_back_squat"\n'
        b'until = 2026-10-31\nbecause = "fatigue"\ntext = "Hold through October."\n'
        b'[decision.override]\nkind = "hold"\n',
        file="d.toml",
        clock=FixedClock(),
    )

    assert codes(flags(conn, HOLD), "override_persisting") == []


def test_a_line_that_moved_from_the_same_anchor_with_no_override_is_unexplained_drift() -> None:
    conn = a_squat_week()
    plan_id = an_approved_plan(conn, "2026-10-26", approved_at=AFTER_THE_VERSION)
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        "2026-10-26",
        "bb_back_squat",
        set_groups=[{**SQUAT_GROUPS[0], "load": 110.0, "load_kg": 49.9}],
        change="held",
        derived_from="exposure:h-1/bb_back_squat",
    )

    [drift] = codes(flags(conn), "unexplained_drift")
    explained = codes(flags(conn, HOLD), "unexplained_drift")

    assert drift.params["last_prescription"] == "4×6–8 at 110 lb"
    assert drift.params["this_prescription"] == "4×6–8 at 125 lb"
    assert explained == []


def test_a_version_adopted_since_the_last_plan_explains_every_change() -> None:
    conn = a_squat_week()
    plan_id = an_approved_plan(conn, "2026-10-26", approved_at="2026-10-26T08:00:00+00:00")
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        "2026-10-26",
        "bb_back_squat",
        set_groups=[{**SQUAT_GROUPS[0], "load": 110.0, "load_kg": 49.9}],
        change="held",
        derived_from="exposure:h-1/bb_back_squat",
    )

    assert codes(flags(conn), "unexplained_drift") == []


def test_a_load_the_last_plan_froze_that_the_rack_cannot_build_is_frozen_load_off_rack() -> None:
    conn = a_squat_week()
    plan_id = an_approved_plan(conn, "2026-10-26")
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        "2026-10-26",
        "bb_back_squat",
        set_groups=[{**SQUAT_GROUPS[0], "load": 121.0}],
        change="held",
    )

    [off] = codes(flags(conn), "frozen_load_off_rack")

    assert off.key == "frozen_load_off_rack@session:2026-11-02/lower"
    assert off.params == {
        "week": "2026-10-26",
        "line": "bb_back_squat",
        "frozen_load": 121.0,
        "location": "home",
    }


def test_a_workout_matched_to_a_light_week_plan_is_skipped_as_the_anchor() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-19", *[(120, 8, 8)] * 4)
    plan_id = an_approved_plan(conn, "2026-10-26", approved_at=AFTER_THE_VERSION)
    a_plan_override(conn, plan_id, "light_week", None, None)
    a_deload_logged(conn)

    assert the_squat_anchor(conn) == "exposure:h-1/bb_back_squat"


def test_a_light_week_line_that_took_the_return_band_still_anchors() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-09-07", *[(120, 8, 8)] * 4)
    plan_id = an_approved_plan(conn, "2026-10-26", approved_at=AFTER_THE_VERSION)
    a_plan_override(conn, plan_id, "light_week", None, None)
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        "2026-10-26",
        "bb_back_squat",
        set_groups=SQUAT_GROUPS,
        change="reset",
        steps=[{"step": "cut", "from": 120, "to": 100, "cause": "return 3–4 wk, 49 days off"}],
    )
    a_deload_logged(conn)

    assert the_squat_anchor(conn) == "exposure:w-0001/bb_back_squat"


def a_deload_logged(conn: Connection) -> None:
    deload = ((80 * KG_PER_LB, 6, 6.0),) * 2
    a_logged_workout(conn, "w-0001", "2026-10-26", (SQUAT_TEMPLATE, deload), session_id="lower")


def the_squat_anchor(conn: Connection) -> str | None:
    drafted = plan_draft(
        conn, config=a_config(), kits=(kit_files(),), clock=FixedClock(), week=NEXT_MONDAY
    )
    [line] = drafted.draft.sessions[0].lines
    return line.derived_from
