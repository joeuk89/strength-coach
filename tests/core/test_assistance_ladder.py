from support.exposures import an_exposure
from support.prescribe import a_line, a_request, working

from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import ExerciseFacts, LinePrescription, Step

RUNGS = [60, 50, 40, 30, 20, 10, 0]
PULL_UP = a_line("assisted_pull_up", working(4, 8), scheme="assistance_ladder", rungs=RUNGS)
ASSISTED = {"assisted_pull_up": ExerciseFacts("assisted", "machine", "vertical_pull")}


def pull_up(*sets: tuple[float, int, float]) -> LinePrescription:
    logged = an_exposure(
        "2026-10-26", *sets, workout_id="h-3", exercise_id="assisted_pull_up", mode="assisted"
    )
    request = a_request(PULL_UP, exposures=(logged,), exercises=ASSISTED)
    return prescribe(request).lines[0]


def test_a_full_hit_moves_one_rung_to_less_assistance() -> None:
    line = pull_up(*[(40, 8, 8)] * 4)

    assert line.steps == (Step("scheme", 40, 30, "hit"),)
    assert line.groups[0].load == Load(30, "assisted")
    assert line.change == "4×8 @8: rung 40 → 30"
    assert line.flags == ()


def test_a_set_short_of_the_reps_holds_the_rung() -> None:
    line = pull_up((40, 8, 8), (40, 8, 8), (40, 8, 8), (40, 7, 8))

    assert (line.change, line.groups[0].load, line.flags) == ("held", Load(40, "assisted"), ())


def test_a_set_at_rpe_two_over_holds_and_warns_rep_range_missed() -> None:
    line = pull_up((40, 8, 8), (40, 8, 8), (40, 8, 9), (40, 8, 10))

    assert line.groups[0].load == Load(40, "assisted")
    assert [(f.code, dict(f.params)) for f in line.flags] == [
        (
            "rep_range_missed",
            {"set_index": 4, "reps": 8, "range": [8, 8], "logged_rpe": 10, "authored_rpe": 8},
        )
    ]


def test_a_hit_on_the_last_rung_holds_there() -> None:
    line = pull_up(*[(0, 8, 8)] * 4)

    assert line.steps == (Step("scheme", 0, 0, "last_rung"),)
    assert (line.change, line.groups[0].load) == ("held", Load(0, "assisted"))


def test_with_no_exposure_the_line_opens_on_the_first_rung() -> None:
    line = prescribe(a_request(PULL_UP, exercises=ASSISTED)).lines[0]

    assert (line.derived_from, line.change) == ("start_load", "first prescription")
    assert line.groups[0].load == Load(60, "assisted")
    assert line.flags == ()


def test_a_logged_load_between_rungs_reads_as_the_rung_with_more_assistance() -> None:
    line = pull_up(*[(35, 8, 8)] * 4)

    assert line.groups[0].load == Load(30, "assisted")
    assert [f.code for f in line.flags] == ["offgrid_anchor_ignored"]
