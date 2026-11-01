import datetime
from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, warm_up, working

from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    LinePrescription,
    NiggleConstraint,
    PlanOverride,
    StatusSpan,
    Step,
)
from coach.core.program.form import Dose, Line, SetGroup

RUNGS = [60, 50, 40, 30, 20, 10, 0]
PULL_UP = a_line("assisted_pull_up", working(4, 8), scheme="assistance_ladder", rungs=RUNGS)


def pull_up_on(
    on: str, rung: float, *, workout_id: str | None = None, last_reps: int = 8
) -> Exposure:
    return an_exposure(
        on,
        *[(rung, 8, 8)] * 3,
        (rung, last_reps, 8),
        workout_id=workout_id,
        exercise_id="assisted_pull_up",
        mode="assisted",
        session_id="lower",
    )


def derive(line: Line, *exposures: Exposure, **request: Any) -> LinePrescription:
    return prescribe(a_request(line, exposures=exposures, **request)).lines[0]


def test_the_assisted_pull_up_after_25_days_off_steps_two_rungs_back_with_one_set_fewer() -> None:
    line = derive(
        PULL_UP,
        pull_up_on("2026-09-24", 40, last_reps=7),
        pull_up_on("2026-10-01", 40, last_reps=7),
        pull_up_on("2026-10-08", 40, last_reps=7),
    )

    assert line.steps[:3] == (
        Step("cut", 40, 60, "return 22–42, 25 days off"),
        Step("cut", 4, 3, "sets"),
        Step("rpe_ceiling", 8, 8, "return_band"),
    )
    assert line.change == "4×8 @8 rung 40 → 3×8 @≤8 rung 60"
    [group] = line.groups
    assert (group.count, group.load, group.reps, group.rpe, group.rpe_cap) == (
        3,
        Load(60, "assisted"),
        8,
        8,
        8,
    )


def test_the_week_after_a_return_climbs_from_the_return_exposure_with_no_band() -> None:
    line = derive(
        PULL_UP,
        pull_up_on("2026-09-24", 40),
        pull_up_on("2026-10-01", 40),
        pull_up_on("2026-10-08", 40),
        pull_up_on("2026-10-26", 60, workout_id="h-return"),
    )

    assert line.derived_from == "exposure:h-return/assisted_pull_up"
    assert [s for s in line.steps if s.step in ("cut", "rpe_ceiling")] == []
    assert [(g.count, g.load, g.rpe_cap) for g in line.groups] == [(4, Load(50, "assisted"), None)]


def squat_on(on: str, *sets: tuple[float, int, float], workout_id: str = "h-1") -> Exposure:
    return an_exposure(
        on, *sets, workout_id=workout_id, exercise_id="bb_back_squat", session_id="lower"
    )


SQUAT_HELD = ((120, 8, 8), (120, 8, 8), (120, 7, 8), (120, 6, 8))
LIGHT_WEEK = PlanOverride("light_week")


def test_a_return_band_inside_a_light_week_applies_the_band_only() -> None:
    line = derive(a_line(), squat_on("2026-10-03", *SQUAT_HELD), overrides=(LIGHT_WEEK,))

    assert line.steps[:3] == (
        Step("cut", 120, 108, "return 22–42, 30 days off"),
        Step("cut", 4, 3, "sets"),
        Step("rpe_ceiling", 8, 8, "return_band"),
    )
    assert "light" not in [s.cause for s in line.steps]
    working = line.groups[-1]
    assert (working.count, working.load, working.rpe_cap) == (3, Load(105, "total"), 8)


def test_a_return_line_inside_a_minimum_week_keeps_its_band() -> None:
    minimum = PlanOverride("minimum_week", params={"keep": ["lower"]})

    line = derive(a_line(), squat_on("2026-10-03", *SQUAT_HELD), overrides=(minimum,))

    assert line.steps[0] == Step("cut", 120, 108, "return 22–42, 30 days off")
    assert (line.groups[-1].count, line.groups[-1].load) == (3, Load(105, "total"))


SQUAT_CAP = NiggleConstraint("n-0001", "load_cap", exercise_id="bb_back_squat", value=100)
SQUAT_CEILING = DecisionInForce(
    "d-0001", "safety_ceiling", exercise_id="bb_back_squat", params={"load": 110}
)


def test_a_niggle_cap_below_a_safety_ceiling_binds_and_the_ceiling_is_not_binding() -> None:
    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        niggle_constraints=(SQUAT_CAP,),
        decisions=(SQUAT_CEILING,),
    )

    assert line.steps[:3] == (
        Step("niggle", 120, 100, "load_cap niggle:n-0001"),
        Step("rack", 100, 100, "row"),
        Step("rack", 110, 100, "not_binding"),
    )
    assert line.groups[-1].load == Load(100, "total")
    assert line.flags == ()


def test_a_safety_ceiling_truncates_the_rack() -> None:
    line = derive(a_line(), squat_on("2026-10-26", *SQUAT_HELD), decisions=(SQUAT_CEILING,))

    assert Step("rack", 120, 110, "safety_ceiling") in line.steps
    assert line.groups[-1].load == Load(110, "total")


def test_a_pin_load_above_a_niggle_cap_is_recovery_ceiling_exceeded() -> None:
    pin = PlanOverride("pin_load", "lower", "bb_back_squat", params={"load": 115})

    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        niggle_constraints=(SQUAT_CAP,),
        overrides=(pin,),
    )

    assert [(f.code, f.severity, dict(f.params)) for f in line.flags] == [
        (
            "recovery_ceiling_exceeded",
            "violation",
            {"ceiling_kind": "niggle", "ceiling": 100, "prescribed": 115, "ref": "niggle:n-0001"},
        )
    ]
    assert line.groups[-1].load == Load(100, "total")


def ill(from_date: str, to_date: str | None) -> StatusSpan:
    return StatusSpan(
        "ill",
        datetime.date.fromisoformat(from_date),
        None if to_date is None else datetime.date.fromisoformat(to_date),
    )


def test_an_ill_span_with_no_exposure_after_it_caps_every_set_at_rpe_7_and_is_not_a_cut() -> None:
    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        status_spans=(ill("2026-10-28", "2026-10-30"),),
    )

    assert [s.step for s in line.steps].count("cut") == 0
    assert Step("rpe_ceiling", 8, 7, "illness") in line.steps
    working = line.groups[-1]
    assert (working.count, working.rpe, working.rpe_cap) == (4, 7, 7)


def test_an_exposure_after_the_ill_span_lifts_the_illness_cap() -> None:
    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        an_exposure("2026-10-31", (60, 10, 6), exercise_id="bb_back_squat"),
        status_spans=(ill("2026-10-20", "2026-10-24"),),
    )

    assert line.groups[-1].rpe_cap is None


def test_illness_with_days_off_over_10_is_a_return_line_with_the_cap_at_7() -> None:
    line = derive(
        a_line(), squat_on("2026-10-15", *SQUAT_HELD), status_spans=(ill("2026-10-18", None),)
    )

    assert line.steps[:4] == (
        Step("cut", 120, 114, "return 11–21, 18 days off"),
        Step("cut", 4, 3, "sets"),
        Step("rpe_ceiling", 8, 7, "illness"),
        Step("rpe_ceiling", 8, 7, "not_binding"),
    )
    assert (line.groups[-1].count, line.groups[-1].rpe_cap) == (3, 7)


HOLD = a_line("bb_bench_press", working(4, 10), scheme="hold")


def bench_on(on: str, load: float = 100) -> Exposure:
    return an_exposure(on, *[(load, 10, 7)] * 4, session_id="lower")


def test_a_hold_line_in_a_light_week_is_still_cut_and_capped() -> None:
    line = derive(HOLD, bench_on("2026-10-26"), overrides=(LIGHT_WEEK,))

    assert Step("cut", 4, 2, "sets") in line.steps
    [group] = line.groups
    assert (group.count, group.load, group.rpe_cap) == (2, Load(100, "total"), 8)


def test_a_hold_line_after_a_layoff_takes_the_return_band() -> None:
    line = derive(HOLD, bench_on("2026-09-01"))

    assert line.steps[0] == Step("cut", 100, 85, "return 43+, 62 days off")
    [group] = line.groups
    assert (group.count, group.load, group.rpe_cap) == (3, Load(85, "total"), 7)


PRIORITY = Dose(per_muscle=10, lift={"bb_bench_press": 8, "assisted_pull_up": 8})
TOP_BACKOFF = a_line(
    "bb_bench_press",
    warm_up(5),
    working(1, 3, 8),
    working(3, 5, None),
    scheme="top_backoff",
    pct_of_top=85,
)


def test_a_priority_lift_under_top_backoff_gets_one_test_single_in_a_light_week() -> None:
    logged = an_exposure("2026-10-26", (100, 3, 8), (85, 5, 6), (85, 5, 6), (85, 5, 6))

    line = derive(TOP_BACKOFF, logged, overrides=(LIGHT_WEEK,), dose=PRIORITY)

    # e1RM 100 × (1 + 5/30) = 116.67; one rep at RPE 9 is 116.67 / (1 + 2/30) = 109.4, down to 105;
    # the back-offs are 85 % of the top
    assert [(g.type, g.count, g.load, g.reps, g.rpe) for g in line.groups[1:]] == [
        ("test", 1, Load(105, "total"), 1, 9),
        ("working", 1, Load(100, "total"), 3, 8),
        ("working", 2, Load(85, "total"), 5, 8),
    ]
    assert line.groups[0].type == "warm_up"


def test_the_assisted_pull_up_under_the_ladder_gets_no_test_single() -> None:
    line = derive(PULL_UP, pull_up_on("2026-10-26", 40), overrides=(LIGHT_WEEK,), dose=PRIORITY)

    assert [g.type for g in line.groups] == ["working"]


def test_a_lift_that_is_not_a_priority_lift_gets_no_test_single() -> None:
    logged = an_exposure("2026-10-26", (100, 3, 8), (85, 5, 6), (85, 5, 6), (85, 5, 6))

    line = derive(TOP_BACKOFF, logged, overrides=(LIGHT_WEEK,))

    assert "test" not in [g.type for g in line.groups]


def test_an_rpe_ceiling_limits_the_load_through_the_e1rm_rounded_down() -> None:
    logged = squat_on("2026-10-26", (120, 6, 9), (120, 6, 9), (120, 6, 9), (120, 6, 9))

    line = derive(a_line(), logged, status_spans=(ill("2026-10-28", "2026-10-30"),))

    # e1RM 120 × (1 + 7/30) = 148; six reps at RPE 7 is 148 / (1 + 9/30) = 113.85
    assert line.steps[:3] == (
        Step("rpe_ceiling", 8, 7, "illness"),
        Step("rpe_ceiling", 120, 113.85, "e1rm"),
        Step("rack", 113.85, 110, "row"),
    )


def test_reps_are_cut_so_a_capped_set_stays_inside_the_model() -> None:
    high_reps = a_line("bb_back_squat", working(3, (10, 12)))
    logged = squat_on("2026-10-26", (100, 10, 8), (100, 10, 8), (100, 10, 8))

    line = derive(high_reps, logged, status_spans=(ill("2026-10-28", "2026-10-30"),))

    assert line.groups[-1].reps == 9


def test_an_rpe_ceiling_limits_the_load_to_fit_the_working_group_with_more_reps() -> None:
    two_groups = a_line("bb_back_squat", working(1, (3, 5)), working(3, (8, 10)))
    logged = squat_on("2026-10-26", (100, 5, 8), (100, 8, 8), (100, 8, 8), (100, 8, 8))

    line = derive(two_groups, logged, status_spans=(ill("2026-10-28", "2026-10-30"),))

    # e1RM 100 × (1 + 10/30) = 133.33; eight reps at RPE 7 is 133.33 / (1 + 11/30) = 97.56
    assert Step("rpe_ceiling", 100, 97.56, "e1rm") in line.steps
    assert [(g.load, g.reps) for g in line.groups] == [
        (Load(95, "total"), (3, 5)),
        (Load(95, "total"), (8, 9)),
    ]


def test_with_no_usable_e1rm_a_capped_line_is_clipped_to_the_anchor_and_warns() -> None:
    logged = squat_on("2026-10-26", *[(120, 15, 7)] * 4)

    line = derive(a_line(), logged, overrides=(LIGHT_WEEK,))

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "rpe_ceiling_unchecked",
            {"cap": 8, "clipped_load": 120, "anchor_exposure": "exposure:h-1/bb_back_squat"},
        )
    ]
    assert line.groups[-1].load == Load(120, "total")


def test_a_light_week_restating_the_load_cut_cuts_load_and_sets() -> None:
    restated = PlanOverride("light_week", params={"load_cut_pct": 10})

    line = derive(a_line(), squat_on("2026-10-26", *SQUAT_HELD), overrides=(restated,))

    assert line.steps[:2] == (Step("cut", 120, 108, "light"), Step("cut", 4, 2, "sets"))
    working = line.groups[-1]
    assert (working.count, working.load, working.rpe_cap) == (2, Load(105, "total"), 8)


def test_an_avoid_constraint_on_the_pattern_drops_the_line() -> None:
    avoid = NiggleConstraint("n-0002", "avoid", pattern="squat")

    line = derive(a_line(), squat_on("2026-10-26", *SQUAT_HELD), niggle_constraints=(avoid,))

    assert (line.groups, line.change) == ((), "dropped")
    assert line.steps == (Step("niggle", None, None, "avoid niggle:n-0002"),)


def test_no_added_load_caps_a_hit_at_the_anchor_load() -> None:
    hit = squat_on("2026-10-26", *[(120, 8, 8)] * 4)
    global_cap = NiggleConstraint("n-0003", "no_added_load")

    line = derive(a_line(), hit, niggle_constraints=(global_cap,))

    assert Step("niggle", 125, 120, "no_added_load niggle:n-0003") in line.steps
    assert line.groups[-1].load == Load(120, "total")


def test_the_strictest_of_two_open_niggles_binds() -> None:
    looser = NiggleConstraint("n-0004", "load_cap", exercise_id="bb_back_squat", value=110)

    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        niggle_constraints=(looser, SQUAT_CAP),
    )

    assert line.groups[-1].load == Load(100, "total")


def test_a_niggle_cap_looser_than_the_return_band_is_not_binding() -> None:
    looser = NiggleConstraint("n-0004", "load_cap", exercise_id="bb_back_squat", value=110)

    line = derive(a_line(), squat_on("2026-10-03", *SQUAT_HELD), niggle_constraints=(looser,))

    assert line.steps[:3] == (
        Step("cut", 120, 108, "return 22–42, 30 days off"),
        Step("cut", 4, 3, "sets"),
        Step("niggle", 110, 108, "not_binding"),
    )
    assert line.flags == ()


def test_a_niggle_rpe_cap_on_the_pattern_is_an_rpe_ceiling() -> None:
    cap = NiggleConstraint("n-0005", "rpe_cap", pattern="squat", value=6)

    line = derive(a_line(), squat_on("2026-10-26", *SQUAT_HELD), niggle_constraints=(cap,))

    assert Step("rpe_ceiling", 8, 6, "niggle:n-0005") in line.steps
    assert line.groups[-1].rpe_cap == 6


def test_a_pin_load_over_the_return_band_is_return_band_disagrees() -> None:
    pin = PlanOverride("pin_load", "lower", "bb_back_squat", params={"load": 115})

    line = derive(a_line(), squat_on("2026-10-03", *SQUAT_HELD), overrides=(pin,))

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "return_band_disagrees",
            {"days_off": 30, "band": "22–42", "load": 108, "set_delta": -1, "rpe_cap": 8},
        )
    ]
    assert line.groups[-1].load == Load(105, "total")


def test_a_pin_load_over_a_safety_ceiling_is_load_off_grid() -> None:
    pin = PlanOverride("pin_load", "lower", "bb_back_squat", params={"load": 120})

    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        decisions=(SQUAT_CEILING,),
        overrides=(pin,),
    )

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "load_off_grid",
            {
                "load": 120,
                "implement": "barbell",
                "location": "home",
                "nearest_grid_loads": [110],
            },
        )
    ]


def test_an_off_grid_pin_over_a_safety_ceiling_is_one_flag_naming_the_ceiling() -> None:
    pin = PlanOverride("pin_load", "lower", "bb_back_squat", params={"load": 121})

    line = derive(
        a_line(),
        squat_on("2026-10-26", *SQUAT_HELD),
        decisions=(SQUAT_CEILING,),
        overrides=(pin,),
    )

    assert [(f.code, f.params["nearest_grid_loads"], f.message) for f in line.flags] == [
        ("load_off_grid", [110], "the pinned 121 is over the safety ceiling of 110")
    ]


def test_a_wave_531_return_line_drops_the_rep_out_and_cuts_the_training_max() -> None:
    wave = a_line("bb_bench_press", SetGroup(3, "working"), scheme="wave_531", start_load=100)
    logged = an_exposure("2026-10-03", (65, 5, None), (75, 5, None), (85, 8, None))

    line = derive(wave, logged, racks={"barbell": a_rack(*[50 + 2.5 * i for i in range(21)])})

    # 30 days off is the 22–42 band: each wave load × 0.90, the last set gone
    assert Step("cut", (65, 75, 85), (58.5, 67.5, 76.5), "return 22–42, 30 days off") in line.steps
    assert [(g.count, g.load, g.reps) for g in line.groups] == [
        (1, Load(57.5, "total"), 5),
        (1, Load(67.5, "total"), 5),
    ]


def test_a_wave_531_return_line_cuts_the_training_max_before_rounding_once() -> None:
    wave = a_line("bb_bench_press", SetGroup(3, "working"), scheme="wave_531", start_load=107)
    logged = an_exposure("2026-10-03", (70, 5, None), (80, 5, None), (90, 8, None))

    line = derive(wave, logged, racks={"barbell": a_rack(*[50 + 2.5 * i for i in range(21)])})

    # 107 × 0.65 × 0.90 is 62.6, one row down to 62.5; rounding each wave load first gives 60
    assert [(g.count, g.load, g.reps) for g in line.groups] == [
        (1, Load(62.5, "total"), 5),
        (1, Load(70, "total"), 5),
    ]
