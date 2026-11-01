from typing import Any

from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, working

from coach.core.exposure import Exposure
from coach.core.linear import Reset, resets
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, NiggleConstraint, Step

BENCH = a_line("bb_bench_press", working(4, 5), scheme="linear")
RACK = a_rack(100, 105, 107.5, 110, 115, 120, 125)


def bench_on(on: str, load: float, *reps: int) -> Exposure:
    return an_exposure(on, *[(load, r, 8) for r in reps], session_id="lower")


def derive(*exposures: Exposure, **request: Any) -> LinePrescription:
    built = a_request(BENCH, exposures=exposures, racks={"barbell": RACK}, **request)
    return prescribe(built).lines[0]


def test_one_miss_holds_at_the_anchor_load() -> None:
    line = derive(bench_on("2026-10-26", 120, 5, 5, 5, 4))

    assert (line.change, line.groups[0].load) == ("held", Load(120, "total"))


def test_the_second_consecutive_miss_at_one_load_resets_to_0_9_rounded_down() -> None:
    line = derive(
        bench_on("2026-10-19", 120, 5, 5, 5, 4),
        bench_on("2026-10-26", 120, 5, 5, 4, 3),
    )

    assert line.steps[0] == Step("scheme", 120, 107.5, "reset, misses 2")
    assert line.change == "reset 120 → 107.5"
    assert line.groups[0].load == Load(107.5, "total")


def test_a_reset_lowered_further_by_a_niggle_cap_reports_the_load_prescribed() -> None:
    cap = NiggleConstraint("n-0001", "load_cap", exercise_id="bb_bench_press", value=100)

    line = derive(
        bench_on("2026-10-19", 120, 5, 5, 5, 4),
        bench_on("2026-10-26", 120, 5, 5, 4, 3),
        niggle_constraints=(cap,),
    )

    assert (line.change, line.groups[0].load) == ("4×5 @8: 120 → 100", Load(100, "total"))


def test_an_exposure_at_the_reset_load_restarts_the_miss_count() -> None:
    line = derive(
        bench_on("2026-10-12", 120, 5, 5, 5, 4),
        bench_on("2026-10-19", 120, 5, 5, 4, 3),
        bench_on("2026-10-26", 107.5, 5, 5, 5, 4),
    )

    assert (line.change, line.groups[0].load) == ("held", Load(107.5, "total"))


def test_a_set_never_logged_is_not_a_miss() -> None:
    line = derive(
        bench_on("2026-10-19", 120, 5, 5, 5, 4),
        bench_on("2026-10-26", 120, 5, 5, 5),
    )

    assert (line.change, line.groups[0].load) == ("held", Load(120, "total"))


def test_a_younger_athletes_reset_factor_is_named_on_the_line() -> None:
    younger = a_line("bb_bench_press", working(4, 5), scheme="linear", reset_factor=0.95)
    exposures = (bench_on("2026-10-19", 120, 5, 5, 5, 4), bench_on("2026-10-26", 120, 5, 5, 4, 3))

    line = prescribe(a_request(younger, exposures=exposures, racks={"barbell": RACK})).lines[0]

    assert line.groups[0].load == Load(110, "total")


def test_resets_per_lift_are_derived_from_history() -> None:
    history = (
        bench_on("2026-09-28", 120, 5, 5, 5, 4),
        bench_on("2026-10-05", 120, 5, 5, 4, 3),
        bench_on("2026-10-12", 107.5, 5, 5, 5, 5),
        bench_on("2026-10-19", 110, 5, 5, 5, 5),
    )

    assert resets(BENCH, history, RACK, "total") == (
        Reset("exposure:w-2026-10-12/bb_bench_press", 120, 107.5),
    )
