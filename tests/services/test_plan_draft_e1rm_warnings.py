import datetime
import tomllib

from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_squat_program, squat_logged
from support.program_drafts import a_session
from support.programs import a_config

from coach.core.flag import Flag
from coach.core.overrides import parse_plan_overrides
from coach.services.plan_draft import plan_draft
from coach.store.connection import Connection

NEXT_MONDAY = datetime.date(2026, 11, 2)
PIN_150 = """\
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 150
because = "athlete_request"
text = "Wants to try a heavy day."
"""


def raised(conn: Connection, code: str, overrides: str = "") -> list[Flag]:
    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
        week=NEXT_MONDAY,
        overrides=parse_plan_overrides(tomllib.loads(overrides), file="plan.toml"),
    ).draft
    return [flag for flag in draft.flags if flag.code == code]


def test_a_pinned_top_set_beyond_failure_on_the_e1rm_is_top_set_above_e1rm() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)

    [flag] = raised(conn, "top_set_above_e1rm", PIN_150)

    assert flag.key == "top_set_above_e1rm@line:2026-11-02/lower/bb_back_squat"
    assert flag.severity == "warning"
    assert flag.rn == "rn:autoregulation.6"
    assert flag.params == {"e1rm": 160, "model": 126.32, "load": 150, "rpe_target": 8}


def test_the_scheme_step_inside_the_model_raises_no_top_set_above_e1rm() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)

    assert raised(conn, "top_set_above_e1rm") == []


def test_an_e1rm_from_sets_logged_without_rpe_raises_no_top_set_above_e1rm() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, None)] * 4)

    assert raised(conn, "top_set_above_e1rm", PIN_150) == []


def test_an_anchor_set_further_from_failure_than_the_cap_is_over_rep_cap() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", (120, 8, 8), (120, 8, 5), (120, 8, 6), (120, 8, 8))

    [flag] = raised(conn, "over_rep_cap")

    assert flag.key == "over_rep_cap@exposure:h-1/bb_back_squat"
    assert flag.severity == "warning"
    assert flag.rn == "rn:autoregulation.5"
    assert flag.params == {"reps": 13, "cap": 12}


def test_an_anchor_inside_the_cap_raises_no_over_rep_cap() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)

    assert raised(conn, "over_rep_cap") == []


def test_a_line_authored_over_the_cap_raises_no_over_rep_cap() -> None:
    high_reps = {**SQUAT_LINE, "sets": [{"count": 3, "reps": [12, 15], "rpe": 8}]}
    conn = a_squat_program(a_session("lower", high_reps))
    squat_logged(conn, "h-1", "2026-10-26", *[(80, 15, 8)] * 3)

    assert raised(conn, "over_rep_cap") == []
