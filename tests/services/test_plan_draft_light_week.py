import datetime

from support.clock import FixedClock
from support.closed_weeks import a_hard_squat_week, closed_through, monday
from support.kit_fixtures import kit_files
from support.plans import SQUAT_LINE, a_plan_override, a_squat_program, an_approved_plan
from support.program_drafts import a_line, a_session
from support.programs import a_config

from coach.core.flag import Flag
from coach.core.prescription import PlanOverride
from coach.services.plan_draft import plan_draft
from coach.store.connection import Connection

LIGHT = PlanOverride("light_week", because="fatigue", text="Time for a light week.")
INTERVALS = a_session(
    "intervals",
    a_line("pull_up", scheme={"name": "hold"}, start_load=None),
    kind="conditioning",
    scheme={
        "name": "emom_density",
        "minutes": 12,
        "minutes_cap": 16,
        "minutes_step": 2,
        "reps": {"kb_swing": 12},
        "reps_cap": {"kb_swing": 15},
        "rpe_target": 8,
    },
)


def flags_of(conn: Connection, week: str, *overrides: PlanOverride) -> dict[str, Flag]:
    monday_ = datetime.date.fromisoformat(week)
    day_before = monday_ - datetime.timedelta(days=1)
    draft = plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime(day_before.year, day_before.month, day_before.day)),
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


def test_a_light_week_with_no_proposal_standing_warns_light_week_unprompted() -> None:
    flag = flags_of(hard_weeks(3), monday(3), LIGHT)["light_week_unprompted"]

    assert flag.params == {"hard_weeks": 3, "ceiling": 6}


def test_a_light_week_holding_the_load_the_ceiling_proposed_to_cut_is_off_trigger() -> None:
    flags = flags_of(hard_weeks(6), monday(6), LIGHT)

    assert "light_week_unprompted" not in flags
    assert flags["light_week_shape_off_trigger"].params == {
        "proposed_shape": {"set_cut_pct": 40, "load_cut_pct": 10, "rpe_cap": 8},
        "plan_shape": {"set_cut_pct": 40, "load_cut_pct": 0, "rpe_cap": 8},
        "triggers": ["ceiling"],
    }


def test_a_light_week_in_the_proposed_shape_warns_neither() -> None:
    restated = PlanOverride(
        "light_week", params={"load_cut_pct": 10}, because="fatigue", text="As proposed."
    )

    flags = flags_of(hard_weeks(6), monday(6), restated)

    assert not {"light_week_unprompted", "light_week_shape_off_trigger"} & set(flags)


def test_a_superseding_draft_judges_its_light_week_against_the_proposal_it_replaces() -> None:
    restated = PlanOverride(
        "light_week", params={"load_cut_pct": 10}, because="fatigue", text="As proposed."
    )
    conn = hard_weeks(6)
    plan_id = an_approved_plan(conn, monday(6), approved_at="2026-12-13T21:00:00+00:00")
    a_plan_override(conn, plan_id, "light_week", None, None)

    flags = flags_of(conn, monday(6), restated)

    assert not {"light_week_unprompted", "light_week_shape_off_trigger"} & set(flags)


def test_quality_conditioning_the_day_before_a_heavy_squat_suggests_dropping_it() -> None:
    conn = a_squat_program(
        a_session("lower", SQUAT_LINE),
        INTERVALS,
        schedule={"rotation": ["A"], "A": {"tue": "intervals", "wed": "lower"}},
    )

    flag = flags_of(conn, monday(0))["session_drop_suggested"]

    assert flag.scope.session_id == "intervals"
    assert flag.params == {
        "reason": "quality_stack",
        "evidence": ["planned_session:2026-11-03/intervals", "planned_session:2026-11-04/lower"],
    }


def test_standing_quality_conditioning_beside_a_monday_lift_suggests_no_drop() -> None:
    conn = a_squat_program(a_session("lower", SQUAT_LINE), {**INTERVALS, "cadence": "standing"})

    flags = flags_of(conn, monday(0))

    assert "session_drop_suggested" not in flags
