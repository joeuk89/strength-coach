from support.exposures import an_exposure
from support.prescribe import a_line, a_request, working

from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    LinePrescription,
    PlanOverride,
    SessionPrescription,
    Step,
)
from coach.core.program.form import SetGroup

HIT = ((120, 8, 7.5), (120, 8, 8), (120, 8, 8), (120, 8, 8))
SQUAT_HIT = an_exposure("2026-10-26", *HIT, workout_id="h-1", exercise_id="bb_back_squat")


def on_squat(kind: str, **params: object) -> PlanOverride:
    return PlanOverride(kind, "lower", "bb_back_squat", params=params)


def a_decision(kind: str, **params: object) -> DecisionInForce:
    return DecisionInForce(
        "d-0001", "override", "lower", "bb_back_squat", {"override": {"kind": kind, **params}}
    )


def derived(
    *overrides: PlanOverride,
    exposures: tuple[Exposure, ...] = (SQUAT_HIT,),
    decisions: tuple[DecisionInForce, ...] = (),
) -> SessionPrescription:
    request = a_request(a_line(), exposures=exposures, overrides=overrides, decisions=decisions)
    return prescribe(request)


def the_line(
    *overrides: PlanOverride,
    exposures: tuple[Exposure, ...] = (SQUAT_HIT,),
    decisions: tuple[DecisionInForce, ...] = (),
) -> LinePrescription:
    [line] = derived(*overrides, exposures=exposures, decisions=decisions).lines
    return line


def test_a_swap_runs_the_other_exercise_from_its_start_load() -> None:
    line = the_line(on_squat("swap_exercise", to="goblet_squat", start_load=25))

    assert line.exercise_id == "goblet_squat"
    assert line.derived_from == "start_load"
    assert line.steps[:3] == (
        Step("override", "bb_back_squat", "goblet_squat", "swap_exercise"),
        Step("scheme", None, 25, "start_load"),
        Step("rack", 25, 25, "row"),
    )
    assert line.groups[-1].load == Load(25, "single_implement")


def test_a_swap_reads_the_other_exercises_own_history_never_the_squats() -> None:
    goblet = an_exposure(
        "2026-10-20",
        (25, 8, 9),
        workout_id="g-1",
        exercise_id="goblet_squat",
        mode="single_implement",
    )

    line = the_line(
        on_squat("swap_exercise", to="goblet_squat", start_load=10),
        exposures=(SQUAT_HIT, goblet),
    )

    assert line.derived_from == "exposure:g-1/goblet_squat"
    assert line.groups[-1].load == Load(25, "single_implement")


def test_a_swap_with_no_history_and_no_start_load_is_start_load_missing() -> None:
    line = the_line(on_squat("swap_exercise", to="goblet_squat"))

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        ("start_load_missing", {"exercise_id": "goblet_squat"})
    ]
    assert line.groups[-1].load is None


def test_a_swap_to_an_exercise_outside_the_library_is_unknown_exercise() -> None:
    line = the_line(on_squat("swap_exercise", to="sled_push"))

    assert [f.code for f in line.flags] == ["unknown_exercise"]


def test_a_pin_replaces_the_working_load_and_still_rounds_to_the_rack() -> None:
    line = the_line(on_squat("pin_load", load=101))

    assert line.steps[:3] == (
        Step("scheme", 120, 125, "hit"),
        Step("override", 125, 101, "pin_load"),
        Step("rack", 101, 100, "row"),
    )
    assert line.groups[-1].load == Load(100, "total")
    assert line.change == "4×6–8 @8: 120 → 100"


def test_a_pin_between_grid_loads_is_load_off_grid_naming_the_rows_either_side() -> None:
    line = the_line(on_squat("pin_load", load=101))

    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "load_off_grid",
            {
                "load": 101,
                "implement": "barbell",
                "location": "home",
                "nearest_grid_loads": [100, 105],
            },
        )
    ]


def test_a_pin_more_than_one_row_above_the_anchor_warns_increment_over_step() -> None:
    line = the_line(on_squat("pin_load", load=130))

    assert line.groups[-1].load == Load(130, "total")
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "increment_over_step",
            {"increment": 10, "scheme_step": 5, "from_exposure": "exposure:h-1/bb_back_squat"},
        )
    ]


def test_a_pin_over_the_top_of_the_rack_names_the_top_row_alone() -> None:
    line = the_line(on_squat("pin_load", load=195))

    [off_grid] = [f for f in line.flags if f.code == "load_off_grid"]
    assert off_grid.params["nearest_grid_loads"] == [190]
    assert off_grid.message == "the pinned 195 is not on the barbell grid at home; nearest 190"


def test_a_pin_one_row_above_the_anchor_raises_nothing() -> None:
    assert the_line(on_squat("pin_load", load=125)).flags == ()


def test_hold_repeats_the_anchors_dose_with_no_scheme_step() -> None:
    line = the_line(on_squat("hold"))

    assert line.groups[-1].load == Load(120, "total")
    assert line.steps[0] == Step("override", None, 120, "hold")
    assert line.change == "held"


def test_restate_sets_replaces_the_groups_and_the_hit_test_reads_the_version() -> None:
    line = the_line(on_squat("restate_sets", sets=(SetGroup(3, "working", 5, None, 7),)))

    assert [(g.type, g.count, g.reps, g.rpe, g.load) for g in line.groups] == [
        ("working", 3, 5, 7, Load(125, "total"))
    ]
    assert Step("override", 4, 3, "restate_sets") in line.steps


def test_drop_line_ends_the_line() -> None:
    assert derived(on_squat("drop_line")).lines == ()


def test_an_override_decision_in_force_applies_itself() -> None:
    line = the_line(decisions=(a_decision("pin_load", load=110),))

    assert line.groups[-1].load == Load(110, "total")
    assert Step("decision", 125, 110, "pin_load") in line.steps


def test_the_plans_override_beats_a_decision_of_the_same_kind_on_the_same_line() -> None:
    line = the_line(on_squat("pin_load", load=100), decisions=(a_decision("pin_load", load=110),))

    assert line.groups[-1].load == Load(100, "total")
    assert [s.step for s in line.steps if s.cause == "pin_load"] == ["override"]


def test_a_decision_of_another_kind_still_applies_beside_the_plans() -> None:
    line = the_line(
        on_squat("restate_sets", sets=(working(3, 5, 7),)),
        decisions=(a_decision("pin_load", load=110),),
    )

    assert [(g.count, g.load) for g in line.groups] == [(3, Load(110, "total"))]


def test_an_override_on_another_line_leaves_this_one_alone() -> None:
    other = PlanOverride("pin_load", "lower", "bb_bench_press", params={"load": 50})

    assert the_line(other).groups[-1].load == Load(125, "total")


def test_a_pin_on_a_line_with_no_exposure_and_no_start_load_sets_the_working_load() -> None:
    line = the_line(on_squat("pin_load", load=101), exposures=())

    assert line.steps[:2] == (
        Step("override", None, 101, "pin_load"),
        Step("rack", 101, 100, "row"),
    )
    assert line.groups[-1].load == Load(100, "total")
    assert [f.code for f in line.flags] == ["load_off_grid"]


def test_a_pin_on_a_swap_with_no_history_and_no_start_load_sets_the_working_load() -> None:
    line = the_line(on_squat("swap_exercise", to="goblet_squat"), on_squat("pin_load", load=20))

    assert line.exercise_id == "goblet_squat"
    assert line.groups[-1].load == Load(20, "single_implement")
    assert line.flags == ()
