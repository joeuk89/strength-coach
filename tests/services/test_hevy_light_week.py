"""A Hevy workout carries its derived Match, so the light-week and return-band rules of the
anchor and the stall read (docs/spec/prescription.md) hold for it."""

import datetime
from collections.abc import Mapping, Sequence

from support.clock import FixedClock
from support.closed_weeks import SQUAT_WORKING, monday
from support.kit_fixtures import kit_files
from support.plans import (
    a_frozen_prescription,
    a_plan_override,
    a_squat_program,
    an_approved_plan,
    squat_logged,
)
from support.programs import a_config

from coach.core.prescription import LinePrescription
from coach.services.plan_draft import plan_draft
from coach.store.connection import Connection

RETURN_STEP = {"step": "cut", "from": 120, "to": 100, "cause": "return 3–4 wk, 49 days off"}


def a_squat_week(
    conn: Connection,
    week: int,
    lb: float,
    *,
    light: bool = False,
    steps: Sequence[Mapping[str, object]] = (),
) -> None:
    plan_id = an_approved_plan(conn, monday(week))
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        monday(week),
        "bb_back_squat",
        set_groups=[SQUAT_WORKING],
        change="held",
        steps=steps,
    )
    if light:
        a_plan_override(conn, plan_id, "light_week", None, None)
    squat_logged(conn, f"h-{week}", monday(week), *[(lb, 6, 8)] * 4)


def squat_in_week(conn: Connection, week: int) -> LinePrescription:
    on = datetime.date.fromisoformat(monday(week))
    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime.combine(on, datetime.time()) - datetime.timedelta(1)),
        week=on,
        position="A",
    ).draft
    [session] = draft.sessions
    [line] = session.lines
    return line


def test_a_hevy_workout_matched_into_a_light_week_is_skipped_as_the_anchor() -> None:
    conn = a_squat_program()
    a_squat_week(conn, 0, 120)
    a_squat_week(conn, 1, 100, light=True)

    assert squat_in_week(conn, 2).derived_from == "exposure:h-0/bb_back_squat"


def test_a_hevy_workout_on_a_line_that_took_the_return_band_in_a_light_week_anchors() -> None:
    conn = a_squat_program()
    a_squat_week(conn, 0, 120)
    a_squat_week(conn, 1, 100, light=True, steps=[RETURN_STEP])

    assert squat_in_week(conn, 2).derived_from == "exposure:h-1/bb_back_squat"


def test_the_stall_read_skips_a_hevy_workout_matched_into_a_light_week() -> None:
    conn = a_squat_program()
    a_squat_week(conn, 0, 120)
    a_squat_week(conn, 1, 120)
    a_squat_week(conn, 2, 130, light=True)
    a_squat_week(conn, 3, 120)

    [stall] = [f for f in squat_in_week(conn, 4).flags if f.code == "stall_streak"]

    assert stall.params["exposures"] == [
        "exposure:h-0/bb_back_squat",
        "exposure:h-1/bb_back_squat",
        "exposure:h-3/bb_back_squat",
    ]
