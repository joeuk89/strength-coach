from support.exposures import an_exposure
from support.prescribe import a_line, a_rack, a_request, working

from coach.core.exposure import Exposure
from coach.core.linear import Reset, resets
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import LinePrescription, Step

BENCH = a_line("bb_bench_press", working(4, 5), scheme="linear")
RACK = a_rack(100, 105, 107.5, 110, 115, 120, 125)


def bench(*exposures: Exposure) -> LinePrescription:
    request = a_request(BENCH, exposures=exposures, racks={"barbell": RACK})
    return prescribe(request).lines[0]


WEEK_1_MISS = an_exposure("2026-10-19", (120, 5, 8), (120, 5, 8), (120, 5, 8), (120, 4, 9))
WEEK_2_MISS = an_exposure("2026-10-26", (120, 5, 8), (120, 5, 9), (120, 4, 9), (120, 3, 10))


def test_one_miss_holds_at_the_anchor_load() -> None:
    line = bench(WEEK_1_MISS)

    assert (line.change, line.groups[0].load) == ("held", Load(120, "total"))


def test_the_second_consecutive_miss_at_one_load_resets_rounded_down_to_the_rack() -> None:
    line = bench(WEEK_1_MISS, WEEK_2_MISS)

    assert line.steps[0] == Step("scheme", 120, 107.5, "reset, misses 2")
    assert line.change == "reset 120 → 107.5"
    assert line.groups[0].load == Load(107.5, "total")


def test_an_exposure_at_the_reset_load_restarts_the_miss_count() -> None:
    lighter = an_exposure("2026-10-29", (107.5, 5, 8), (107.5, 5, 8), (107.5, 5, 9), (107.5, 4, 9))

    line = bench(WEEK_1_MISS, WEEK_2_MISS, lighter)

    assert (line.change, line.groups[0].load) == ("held", Load(107.5, "total"))


def test_a_younger_athletes_reset_factor_is_named_on_the_line() -> None:
    line = a_line("bb_bench_press", working(4, 5), scheme="linear", reset_factor=0.95)
    request = a_request(line, exposures=(WEEK_1_MISS, WEEK_2_MISS), racks={"barbell": RACK})

    assert prescribe(request).lines[0].groups[0].load == Load(110, "total")


def test_a_set_never_logged_is_incomplete_and_does_not_count_as_a_miss() -> None:
    incomplete = an_exposure("2026-10-26", (120, 5, 8), (120, 5, 8), (120, 5, 8))

    line = bench(WEEK_1_MISS, incomplete)

    assert line.change == "held"


def test_resets_per_lift_derive_from_history() -> None:
    after_reset = an_exposure("2026-10-29", *[(107.5, 5, 8)] * 4, workout_id="w-reset")
    newest_first = (after_reset, WEEK_2_MISS, WEEK_1_MISS)

    assert resets(BENCH, newest_first, RACK, "total") == (
        Reset("exposure:w-reset/bb_bench_press", 120, 107.5),
    )


def test_a_lighter_exposure_after_one_miss_is_not_a_reset() -> None:
    lighter = an_exposure("2026-10-26", *[(110, 5, 8)] * 4)

    assert resets(BENCH, (lighter, WEEK_1_MISS), RACK, "total") == ()
