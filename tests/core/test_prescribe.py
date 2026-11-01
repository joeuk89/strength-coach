import datetime
from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, facts, warm_up, working

from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, PrescribedGroup, Step
from coach.core.program.form import Line


def squat(*sets: tuple[float | None, int, float | None]) -> LinePrescription:
    exposure = an_exposure("2026-10-26", *sets, workout_id="h-1", exercise_id="bb_back_squat")
    return prescribe(a_request(a_line(), exposures=(exposure,))).lines[0]


def test_a_double_progression_hit_moves_one_rack_row_and_ladders_the_warm_ups() -> None:
    line = squat((120, 8, 7.5), (120, 8, 8), (120, 8, 8), (120, 8, 8))

    assert line.steps == (
        Step("scheme", 120, 125, "hit"),
        Step("rack", 125, 125, "row"),
        Step("warm_up", (62.5, 93.75), (60, 90), "ladder"),
    )
    assert line.change == "4×6–8 @8: 120 → 125"
    assert line.derived_from == "exposure:h-1/bb_back_squat"
    assert [(g.type, g.count, g.load, g.reps, g.rpe) for g in line.groups] == [
        ("warm_up", 1, Load(60, "total"), 5, None),
        ("warm_up", 1, Load(90, "total"), 3, None),
        ("working", 4, Load(125, "total"), (6, 8), 8),
    ]
    assert line.flags == ()


def test_a_double_progression_under_holds_with_no_flag() -> None:
    line = squat((120, 8, 7.5), (120, 8, 8), (120, 7, 8), (120, 6, 8))

    assert line.steps == (
        Step("rack", 120, 120, "row"),
        Step("warm_up", (60, 90), (60, 90), "ladder"),
    )
    assert line.change == "held"
    assert line.groups[-1].load == Load(120, "total")
    assert line.flags == ()


def test_a_double_progression_set_two_rpe_over_holds_and_warns_rep_range_missed() -> None:
    line = squat((120, 8, 7.5), (120, 8, 8), (120, 8, 8), (120, 8, 10))

    assert line.change == "held"
    assert line.groups[-1].load == Load(120, "total")
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "rep_range_missed",
            {"set_index": 4, "reps": 8, "range": [6, 8], "logged_rpe": 10, "authored_rpe": 8},
        )
    ]


def test_a_double_progression_set_below_the_range_warns_rep_range_missed() -> None:
    line = squat((120, 8, 8), (120, 8, 8), (120, 7, 8), (120, 5, 8))

    assert [f.code for f in line.flags] == ["rep_range_missed"]
    assert line.change == "held"


def test_fewer_working_sets_than_authored_is_not_a_hit_and_raises_nothing() -> None:
    line = squat((120, 8, 7), (120, 8, 7), (120, 8, 7))

    assert line.change == "held"
    assert line.flags == ()


def test_extra_logged_sets_are_ignored() -> None:
    line = squat((120, 8, 7), (120, 8, 7), (120, 8, 7), (120, 8, 7), (120, 3, 10))

    assert line.change == "4×6–8 @8: 120 → 125"


def test_a_set_with_no_rpe_counts_as_on_target() -> None:
    line = squat((120, 8, None), (120, 8, None), (120, 8, None), (120, 8, None))

    assert line.change == "4×6–8 @8: 120 → 125"


def test_a_set_logged_over_the_authored_rpe_is_not_a_hit() -> None:
    line = squat((120, 8, 8), (120, 8, 8), (120, 8, 8), (120, 8, 9))

    assert (line.change, line.flags) == ("held", ())


def test_a_double_progression_set_dropped_below_the_anchor_load_is_not_a_hit() -> None:
    line = squat((120, 8, 8), (120, 8, 8), (90, 8, 8), (90, 8, 8))

    assert (line.change, line.flags) == ("held", ())
    assert line.groups[-1].load == Load(120, "total")


def bench(
    line: Line, *sets: tuple[float | None, int, float | None], **request: Any
) -> LinePrescription:
    exposure = an_exposure("2026-10-26", *sets, workout_id="h-2")
    return prescribe(a_request(line, exposures=(exposure,), **request)).lines[0]


LINEAR = a_line("bb_bench_press", working(4, 5), scheme="linear")


def test_linear_every_set_at_the_authored_reps_moves_one_rack_row() -> None:
    line = bench(LINEAR, (120, 5, 8), (120, 5, 8), (120, 5, 7), (120, 5, 8))

    assert line.steps == (Step("scheme", 120, 125, "hit"), Step("rack", 125, 125, "row"))
    assert line.change == "4×5 @8: 120 → 125"


def test_linear_a_short_set_is_a_miss_and_holds() -> None:
    line = bench(LINEAR, (120, 5, 8), (120, 5, 8), (120, 5, 8), (120, 4, 9))

    assert (line.change, line.flags) == ("held", ())
    assert line.groups[0].load == Load(120, "total")


def test_linear_a_set_dropped_below_the_anchor_load_is_a_miss_and_holds() -> None:
    line = bench(LINEAR, (120, 5, 8), (120, 5, 8), (100, 5, 8), (100, 5, 8))

    assert (line.change, line.flags) == ("held", ())
    assert line.groups[0].load == Load(120, "total")


def test_linear_off_rack_sets_at_the_anchor_used_still_hit() -> None:
    line = bench(LINEAR, (121, 5, 8), (121, 5, 8), (120, 5, 8), (120, 5, 8))

    assert line.change == "4×5 @8: 120 → 125"


def test_hold_repeats_the_anchor_top_load_with_the_authored_sets() -> None:
    held = a_line("bb_bench_press", working(3, 10), scheme="hold")

    line = bench(held, (100, 10, 6), (100, 10, 6), (100, 10, 6))

    assert line.change == "held"
    assert [(g.count, g.load, g.reps) for g in line.groups] == [(3, Load(100, "total"), 10)]


def test_a_line_with_no_exposure_and_no_start_load_is_start_load_missing() -> None:
    line = prescribe(a_request(a_line())).lines[0]

    assert [(f.code, f.severity, dict(f.params)) for f in line.flags] == [
        ("start_load_missing", "violation", {"exercise_id": "bb_back_squat"})
    ]
    assert line.derived_from == "start_load"
    assert all(group.load is None for group in line.groups)


def test_a_start_load_prescribes_at_the_opening_position() -> None:
    line = prescribe(a_request(a_line(start_load=100))).lines[0]

    assert line.derived_from == "start_load"
    assert line.change == "first prescription"
    assert line.groups[-1] == PrescribedGroup("working", 4, Load(100, "total"), (6, 8), None, 8)
    assert line.steps[0] == Step("scheme", None, 100, "start_load")
    assert line.flags == ()


def test_an_exposure_in_another_exercise_does_not_anchor_the_line() -> None:
    other = an_exposure("2026-10-26", (100, 8, 7), exercise_id="bb_bench_press")

    line = prescribe(a_request(a_line(start_load=100), exposures=(other,))).lines[0]

    assert line.derived_from == "start_load"


def test_a_hit_steps_exactly_one_row_on_a_rack_with_gaps() -> None:
    rack = a_rack(100, 102.5, 110, 130)

    line = bench(LINEAR, *[(102.5, 5, 8)] * 4, racks={"barbell": rack})

    assert line.groups[0].load == Load(110, "total")


def test_at_the_top_of_the_rack_a_hit_holds_with_cause_rack_top() -> None:
    line = bench(LINEAR, *[(190, 5, 8)] * 4)

    assert line.steps[0] == Step("scheme", 190, 190, "rack_top")
    assert line.groups[0].load == Load(190, "total")
    assert line.change == "held"


def test_an_off_rack_anchor_takes_the_row_below_and_warns() -> None:
    line = bench(LINEAR, (121, 5, 9), (121, 5, 9), (121, 5, 9), (121, 4, 9))

    assert line.groups[0].load == Load(120, "total")
    assert [(f.code, f.scope.monday) for f in line.flags] == [
        ("offgrid_anchor_ignored", datetime.date(2026, 11, 2))
    ]


def test_a_line_load_mode_with_no_conversion_from_the_exercise_is_load_mode_mismatch() -> None:
    line = prescribe(a_request(a_line(load_mode="bodyweight", start_load=None))).lines[0]

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("load_mode_mismatch", {"exercise_load_mode": "total", "line_load_mode": "bodyweight"})
    ]
    assert all(group.load is None for group in line.groups)


def test_a_per_hand_line_reads_a_total_exposure_as_half_per_hand() -> None:
    lunge = a_line("db_lunge", working(3, (10, 12)), load_mode="per_hand_x2")
    logged = an_exposure("2026-10-26", *[(60, 10, 8)] * 3, exercise_id="db_lunge")

    line = prescribe(
        a_request(lunge, exposures=(logged,), exercises={"db_lunge": facts("total", "dumbbell")})
    ).lines[0]

    assert line.groups[0].load == Load(30, "per_hand_x2")


def test_a_bodyweight_line_carries_no_load_and_no_warm_up_loads() -> None:
    pull_up = a_line("pull_up", warm_up(3), working(3, (6, 10)))
    logged = an_exposure("2026-10-26", *[(None, 10, 7)] * 3, exercise_id="pull_up")

    line = prescribe(a_request(pull_up, exposures=(logged,))).lines[0]

    assert all(group.load is None for group in line.groups)
    assert (line.steps, line.change) == ((), "held")
