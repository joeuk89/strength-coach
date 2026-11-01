import datetime

from support.clock import FixedClock
from support.closed_weeks import a_hard_squat_week, closed_through, monday
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_squat_program
from support.program_drafts import a_line, a_session
from support.programs import a_config

from coach.core.flag import Flag
from coach.core.prescription import PlanOverride
from coach.services.plan_draft import plan_draft
from coach.services.record import record
from coach.store.connection import Connection

DECLINE = """
[[decision]]
kind = "decline_ceiling"
block = "b-2026-10-30"
because = "fatigue"
text = "Feeling fresh; one more hard week."
"""


def clock_on(day: str) -> FixedClock:
    return FixedClock(datetime.datetime.fromisoformat(f"{day}T12:00:00+00:00"))


def flags_of(
    conn: Connection, week: str, *overrides: PlanOverride, today: str | None = None
) -> dict[str, Flag]:
    monday_ = datetime.date.fromisoformat(week)
    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=clock_on(today or (monday_ - datetime.timedelta(days=1)).isoformat()),
        week=monday_,
        overrides=overrides,
        position="A",
    ).draft
    return {flag.code: flag for flag in draft.flags}


def hard_weeks(count: int) -> Connection:
    conn = a_squat_program()
    for n in range(count):
        a_hard_squat_week(conn, monday(n))
    closed_through(conn, count)
    return conn


def test_a_sixth_hard_week_against_a_ceiling_of_6_is_a_violation_on_the_next_plan() -> None:
    flag = flags_of(hard_weeks(6), monday(6))["block_ceiling_exceeded"]

    assert flag.severity == "violation"
    assert flag.params == {"hard_weeks": 6, "ceiling": 6, "block_id": "b-2026-10-30"}
    assert "block_ceiling_exceeded" not in flags_of(hard_weeks(5), monday(5))


def test_a_light_week_or_a_decline_ceiling_clears_the_ceiling() -> None:
    conn = hard_weeks(6)
    light = PlanOverride("light_week", because="fatigue", text="Ceiling reached.")

    assert "block_ceiling_exceeded" not in flags_of(conn, monday(6), light)

    record(conn, DECLINE.encode(), file="d.toml", clock=clock_on("2026-12-13"))
    assert "block_ceiling_exceeded" not in flags_of(conn, monday(6))


def test_the_open_blocks_hard_week_count_reaches_prescribe() -> None:
    conn = hard_weeks(2)

    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=clock_on("2026-11-15"),
        week=datetime.date(2026, 11, 16),
        position="A",
    ).draft

    assert draft.hard_week_count == 2


def test_a_muscle_under_target_in_three_of_four_ordinary_weeks_warns_on_the_plan() -> None:
    flag = flags_of(hard_weeks(4), monday(4))["dose_under_target"]

    assert flag.params["muscle"] == "chest"
    assert flag.params["weekly_figures"] == [0, 0, 0, 0]
    assert "dose_under_target" not in flags_of(hard_weeks(2), monday(2))


def test_a_planned_session_of_12_fractional_sets_warns_session_dose_high() -> None:
    twelve = a_line("bb_back_squat", sets=[{"count": 12, "reps": [6, 8], "rpe": 8}], start_load=100)
    conn = a_squat_program(a_session("lower", twelve))

    flag = flags_of(conn, monday(0))["session_dose_high"]

    assert flag.key == "session_dose_high@session:2026-11-02/lower"
    assert flag.params == {"planned_sets": 12, "ceiling": 11}
    assert "session_dose_high" not in flags_of(a_squat_program(), monday(0))


def test_a_minimum_week_keeping_no_priority_lift_warns_minimum_week_floor() -> None:
    conn = a_squat_program(a_session("lower", SQUAT_LINE), a_session("push"))
    keep = PlanOverride("minimum_week", params={"keep": ("lower",)}, because="schedule", text="t")

    flag = flags_of(conn, monday(0), keep)["minimum_week_floor"]

    assert flag.params == {"priority_lift": "bb_bench_press", "kept_sessions": ["lower"]}
