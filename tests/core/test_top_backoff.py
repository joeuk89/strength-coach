import datetime
from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, warm_up, working

from coach.core.days_off import SessionTrained
from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    ExerciseFacts,
    LinePrescription,
    NiggleConstraint,
    PlanOverride,
    Step,
)

RACK = a_rack(*[70 + 2.5 * i for i in range(27)])
BENCH = a_line(
    "bb_bench_press",
    warm_up(5),
    working(1, 3, 8),
    working(3, 5, None),
    scheme="top_backoff",
    pct_of_top=85,
)


def bench_on(on: str, top_rpe: float, top: float = 100) -> Exposure:
    return an_exposure(on, (top, 3, top_rpe), *[(85, 5, 7)] * 3, session_id="lower")


def derive(*exposures: Exposure, line: Any = BENCH, **request: Any) -> LinePrescription:
    built = a_request(line, exposures=exposures, racks={"barbell": RACK}, **request)
    return prescribe(built).lines[0]


def working_loads(line: LinePrescription) -> list[tuple[int, Load | None]]:
    return [(g.count, g.load) for g in line.groups if g.type == "working"]


def test_an_e1rm_asking_for_two_rows_above_the_anchor_prescribes_one_row_above() -> None:
    # e1RM 100 × (1 + 7/30) = 123.33; three reps at RPE 8 is 105.71, down to 105: two rows up
    line = derive(bench_on("2026-10-26", top_rpe=6))

    assert line.steps[0] == Step("scheme", 100, 102.5, "one_row_cap")
    assert working_loads(line) == [(1, Load(102.5, "total")), (3, Load(87.5, "total"))]
    assert line.change == "1×3 @8 + 3×5: 100 → 102.5"


def test_a_top_the_e1rm_lifts_names_the_e1rm_and_its_exposure_in_the_change() -> None:
    # e1RM 100 × (1 + 6/30) = 120; three reps at RPE 8 is 102.86, down to 102.5
    line = derive(bench_on("2026-10-26", top_rpe=7))

    assert line.steps[0] == Step("scheme", 100, 102.5, "e1rm exposure:w-2026-10-26/bb_bench_press")
    assert line.change == "1×3 @8 + 3×5: 100 → 102.5 (e1RM 120 from 2026-10-26, lower)"


def test_an_e1rm_from_a_workout_that_matched_no_session_is_named_by_its_date_alone() -> None:
    unmatched = an_exposure("2026-10-24", (100, 3, 7), *[(85, 5, 7)] * 3)

    line = derive(unmatched, bench_on("2026-10-26", top_rpe=8))

    assert line.change == "1×3 @8 + 3×5: 100 → 102.5 (e1RM 120 from 2026-10-24)"


def test_the_e1rm_source_stays_on_the_change_when_a_later_step_lowers_the_top() -> None:
    cap = NiggleConstraint("n-0001", "load_cap", exercise_id="bb_bench_press", value=101)

    line = derive(bench_on("2026-10-26", top_rpe=7), niggle_constraints=(cap,))

    assert working_loads(line)[0] == (1, Load(100, "total"))
    assert line.change == "held (e1RM 120 from 2026-10-26, lower)"


def test_an_e1rm_inside_one_row_sets_the_top_rounded_down() -> None:
    # e1RM 100 × (1 + 5.5/30) = 118.33; three reps at RPE 8 is 101.43, down to 100
    line = derive(bench_on("2026-10-26", top_rpe=7.5))

    assert working_loads(line) == [(1, Load(100, "total")), (3, Load(85, "total"))]
    assert line.change == "held"


def test_with_no_e1rm_in_42_days_the_top_holds_and_warns_no_e1rm() -> None:
    trained = (SessionTrained(datetime.date(2026, 10, 26), "lower"),)

    line = derive(bench_on("2026-09-10", top_rpe=6), trained=trained)

    assert working_loads(line) == [(1, Load(100, "total")), (3, Load(85, "total"))]
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("no_e1rm", {"exercise_id": "bb_bench_press", "scheme": "top_backoff"})
    ]


def test_one_bad_day_never_lowers_the_top_set() -> None:
    good = derive(bench_on("2026-10-26", top_rpe=6))

    after_a_bad_day = derive(
        bench_on("2026-10-19", top_rpe=6),
        an_exposure("2026-10-26", (100, 3, 9.5), *[(85, 4, 9)] * 3, session_id="lower"),
    )

    assert working_loads(after_a_bad_day) == working_loads(good)


def test_a_bad_day_at_a_lighter_top_never_lowers_the_top_set() -> None:
    good = derive(bench_on("2026-10-26", top_rpe=8, top=110))

    after_a_bad_day = derive(
        bench_on("2026-10-19", top_rpe=8, top=110),
        an_exposure("2026-10-26", (100, 3, 9.5), *[(85, 4, 9)] * 3, session_id="lower"),
    )

    assert working_loads(good)[0] == (1, Load(110, "total"))
    assert working_loads(after_a_bad_day) == working_loads(good)


def test_with_no_exposure_the_start_load_is_the_top_and_the_back_offs_derive_from_it() -> None:
    opening = a_line(
        "bb_bench_press",
        working(1, 3, 8),
        working(3, 5, None),
        scheme="top_backoff",
        pct_of_top=80,
        start_load=100,
    )

    line = derive(line=opening)

    assert working_loads(line) == [(1, Load(100, "total")), (3, Load(80, "total"))]


def test_a_light_cut_lowers_the_back_offs_with_their_top() -> None:
    light = PlanOverride("light_week", params={"load_cut_pct": 10})

    line = derive(bench_on("2026-10-26", top_rpe=7.5), overrides=(light,))

    assert working_loads(line) == [(1, Load(90, "total")), (2, Load(77.5, "total"))]


def test_a_heavier_top_in_another_session_never_lifts_the_cap_past_one_row() -> None:
    upper = an_exposure("2026-10-23", (110, 3, 8), *[(92.5, 5, 7)] * 3, session_id="upper")

    line = derive(bench_on("2026-10-19", top_rpe=8), upper, bench_on("2026-10-26", top_rpe=8))

    assert working_loads(line)[0] == (1, Load(102.5, "total"))


def test_the_cap_counts_from_the_heaviest_top_in_the_window_not_the_anchors() -> None:
    older = bench_on("2026-10-19", top_rpe=8, top=130)
    bad_day = an_exposure("2026-10-26", (110, 3, 9.5), *[(95, 4, 9)] * 3, session_id="lower")

    line = derive(older, bad_day)

    assert working_loads(line)[0] == (1, Load(130, "total"))


def test_with_no_heavier_top_in_the_window_the_cap_is_one_row_above_the_anchor() -> None:
    # e1RM 110 × (1 + 7/30) = 135.67; three reps at RPE 8 is 116.29, down to 115: capped
    expired = bench_on("2026-09-01", top_rpe=8, top=130)

    line = derive(expired, bench_on("2026-10-26", top_rpe=6, top=110))

    assert working_loads(line)[0] == (1, Load(112.5, "total"))


DEADLIFT = a_line(
    "bb_deadlift", working(1, 6, 7.5), working(2, 6, None), scheme="top_backoff", pct_of_top=85
)
DEADLIFT_RACK = a_rack(*[45 + 2.5 * i for i in range(103)])
HINGE = {"bb_deadlift": ExerciseFacts("total", "barbell", "hinge")}
AUGUST_BEST = an_exposure(
    "2026-08-26", (170.5, 6, 7.5), exercise_id="bb_deadlift", session_id="lower"
)
ON_RAMP = an_exposure("2026-09-16", (135, 6, 6), exercise_id="bb_deadlift", session_id="lower")
RETURN = an_exposure(
    "2026-11-01",
    (112.5, 6, 6),
    exercise_id="bb_deadlift",
    session_id="lower",
    return_band_lines=frozenset({"bb_deadlift"}),
)


def deadlift(
    *exposures: Exposure, on: str, line: Any = DEADLIFT, **request: Any
) -> LinePrescription:
    built = a_request(
        line,
        exposures=exposures,
        racks={"barbell": DEADLIFT_RACK},
        exercises=HINGE,
        on=datetime.date.fromisoformat(on),
        **request,
    )
    return prescribe(built).lines[0]


def codes(line: LinePrescription) -> list[str]:
    return [f.code for f in line.flags]


def test_the_return_week_after_a_layoff_cuts_from_the_anchor_as_before() -> None:
    # 46 days off: 135 × 0.85 = 114.75, down to 112.5, one working set fewer
    line = deadlift(AUGUST_BEST, ON_RAMP, on="2026-11-01")

    assert working_loads(line) == [(1, Load(112.5, "total")), (1, Load(95, "total"))]
    assert "carried_e1rm" not in codes(line)
    assert "no_e1rm" in codes(line)


def test_the_week_after_a_return_carries_the_pre_layoff_e1rm_scaled_by_the_band() -> None:
    # carried 170.5 × (1 + 8.5/30) × 0.85 = 185.99; six at RPE 7.5 is 144.93, down to 142.5,
    # under the cap one row above 170 × 0.85 = 144.5
    line = deadlift(AUGUST_BEST, ON_RAMP, RETURN, on="2026-11-08")

    assert working_loads(line) == [(1, Load(142.5, "total")), (2, Load(120, "total"))]
    assert line.steps[0] == Step("scheme", 112.5, 142.5, "e1rm exposure:w-2026-08-26/bb_deadlift")
    assert line.change == "1×6 @7.5 + 2×6: 112.5 → 142.5 (e1RM 185.99 from 2026-08-26, lower)"
    assert "no_e1rm" not in codes(line)
    carried = next(f for f in line.flags if f.code == "carried_e1rm")
    assert dict(carried.params) == {
        "pre_layoff_exposure": "exposure:w-2026-08-26/bb_deadlift",
        "pre_layoff_e1rm": 218.81,
        "factor": 0.85,
        "carried": 185.99,
        "expires": "2026-12-13",
    }


def test_the_carried_cap_counts_one_row_above_the_scaled_pre_layoff_top() -> None:
    # carried 150 × (1 + 12/30) × 0.85 = 178.5 asks for 139.09; the cap is one row above
    # 150 × 0.85 = 127.5
    high_reps = an_exposure(
        "2026-08-26", (150, 10, 8), exercise_id="bb_deadlift", session_id="lower"
    )

    line = deadlift(high_reps, ON_RAMP, RETURN, on="2026-11-08")

    assert working_loads(line)[0] == (1, Load(130, "total"))
    assert line.steps[0] == Step("scheme", 112.5, 130, "one_row_cap")


def test_a_live_point_at_the_carried_e1rm_ends_it_and_the_cap_counts_from_the_live_tops() -> None:
    # live 135 × (1 + 12/30) = 189 ≥ the carried 185.99: the cap is one row above 135
    caught_up = an_exposure(
        "2026-11-01",
        (135, 12, 10),
        exercise_id="bb_deadlift",
        session_id="lower",
        return_band_lines=frozenset({"bb_deadlift"}),
    )

    line = deadlift(AUGUST_BEST, ON_RAMP, caught_up, on="2026-11-08")

    assert working_loads(line)[0] == (1, Load(137.5, "total"))
    assert "carried_e1rm" not in codes(line)


def test_the_carried_e1rm_binds_42_days_after_the_return_exposure_and_not_43() -> None:
    weekly = tuple(
        SessionTrained(datetime.date(2026, 11, 1) + datetime.timedelta(days=d), "lower")
        for d in range(7, 43, 7)
    )

    day_42 = deadlift(AUGUST_BEST, ON_RAMP, RETURN, on="2026-12-13", trained=weekly)
    day_43 = deadlift(AUGUST_BEST, ON_RAMP, RETURN, on="2026-12-14", trained=weekly)

    assert "carried_e1rm" in codes(day_42)
    assert working_loads(day_42)[0] == (1, Load(142.5, "total"))
    assert "carried_e1rm" not in codes(day_43)
    assert working_loads(day_43)[0] == (1, Load(112.5, "total"))
    assert "no_e1rm" in codes(day_43)


def test_a_layoff_with_no_qualifying_pre_layoff_point_climbs_from_the_return_week() -> None:
    # live 112.5 × (1 + 10/30) = 150 asks for 116.88, down to 115, one row above 112.5
    too_easy = an_exposure(
        "2026-08-26", (150, 15, 6), exercise_id="bb_deadlift", session_id="lower"
    )
    on_ramp = an_exposure("2026-09-16", (135, 15, 6), exercise_id="bb_deadlift", session_id="lower")

    line = deadlift(too_easy, on_ramp, RETURN, on="2026-11-08")

    assert working_loads(line)[0] == (1, Load(115, "total"))
    assert codes(line) == []


def test_an_rpe_ceiling_limits_the_load_through_the_carried_e1rm() -> None:
    # 185.99 / (1 + 10/30) = 139.49, down to 137.5; the live 150 would give 112.5
    cap = NiggleConstraint("n-0001", "rpe_cap", exercise_id="bb_deadlift", value=6)

    line = deadlift(AUGUST_BEST, ON_RAMP, RETURN, on="2026-11-08", niggle_constraints=(cap,))

    assert working_loads(line)[0] == (1, Load(137.5, "total"))


def test_a_top_set_above_the_carried_e1rm_is_judged_on_the_carried_value() -> None:
    pin = PlanOverride("pin_load", "lower", "bb_deadlift", params={"load": 170})

    line = deadlift(AUGUST_BEST, ON_RAMP, RETURN, on="2026-11-08", overrides=(pin,))

    above = next(f for f in line.flags if f.code == "top_set_above_e1rm")
    assert above.params["e1rm"] == 185.99
