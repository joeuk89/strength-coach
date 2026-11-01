import datetime

from support.exposures import an_exposure

from coach.core.config import IncrementImplement
from coach.core.e1rm import E1rm, e1rm, load_for, reps_to_failure
from coach.core.load import Load
from coach.core.rack import grid_rack

PLANNED = datetime.date(2026, 11, 2)
BAR = grid_rack(IncrementImplement(increment=2.5, base=20))


def test_a_set_of_8_at_rpe_8_is_10_reps_from_failure_and_qualifies() -> None:
    assert reps_to_failure(8, 8) == 10
    found = e1rm([an_exposure("2026-10-26", (100, 8, 8))], "bb_bench_press", PLANNED)
    assert found == E1rm(
        Load(133.33, "total"), lower_bound=False, exposure="exposure:w-2026-10-26/bb_bench_press"
    )


def test_a_set_of_15_at_rpe_10_does_not_qualify() -> None:
    assert e1rm([an_exposure("2026-10-26", (60, 15, 10))], "bb_bench_press", PLANNED) is None


def test_the_best_qualifying_point_in_the_window_wins_across_exposures() -> None:
    exposures = [
        an_exposure("2026-10-12", (100, 5, 8), (90, 15, 10)),
        an_exposure("2026-10-19", (105, 3, 9)),
    ]
    found = e1rm(exposures, "bb_bench_press", PLANNED)
    assert found is not None
    assert found.load == Load(123.33, "total")
    assert found.exposure == "exposure:w-2026-10-12/bb_bench_press"


def test_a_point_older_than_42_days_is_outside_the_window() -> None:
    old = an_exposure("2026-09-20", (100, 5, 8))
    assert e1rm([old], "bb_bench_press", PLANNED) is None
    assert e1rm([old], "bb_bench_press", datetime.date(2026, 11, 1)) is not None


def test_an_exposure_on_or_after_the_planned_date_is_not_read() -> None:
    assert e1rm([an_exposure("2026-11-02", (100, 5, 8))], "bb_bench_press", PLANNED) is None


def test_another_exercise_is_not_read() -> None:
    squat = an_exposure("2026-10-26", (140, 5, 8), exercise_id="bb_back_squat")
    assert e1rm([squat], "bb_bench_press", PLANNED) is None


def test_a_set_with_no_rpe_yields_a_lower_bound() -> None:
    found = e1rm([an_exposure("2026-10-26", (100, 6, None))], "bb_bench_press", PLANNED)
    assert found == E1rm(
        Load(120, "total"), lower_bound=True, exposure="exposure:w-2026-10-26/bb_bench_press"
    )


def test_a_newer_heavier_set_over_12_to_failure_invalidates_the_point() -> None:
    point = an_exposure("2026-10-12", (100, 5, 8))
    too_easy = an_exposure("2026-10-19", (105, 10, 6))
    assert e1rm([point, too_easy], "bb_bench_press", PLANNED) is None


def test_a_newer_lighter_set_over_12_to_failure_leaves_the_point() -> None:
    point = an_exposure("2026-10-12", (100, 5, 8))
    light = an_exposure("2026-10-19", (80, 10, 6))
    found = e1rm([point, light], "bb_bench_press", PLANNED)
    assert found is not None and found.load == Load(123.33, "total")


def test_the_invalidation_holds_until_a_newer_qualifying_point_exists() -> None:
    exposures = [
        an_exposure("2026-10-12", (100, 5, 8)),
        an_exposure("2026-10-19", (105, 10, 6)),
        an_exposure("2026-10-26", (90, 8, 8)),
    ]
    found = e1rm(exposures, "bb_bench_press", PLANNED)
    assert found is not None
    assert found.load == Load(120, "total")
    assert found.exposure == "exposure:w-2026-10-26/bb_bench_press"


def test_a_bodyweight_set_carries_no_e1rm() -> None:
    hang = an_exposure("2026-10-26", (None, 8, 8), mode="bodyweight")
    assert e1rm([hang], "bb_bench_press", PLANNED) is None


def test_load_for_inverts_the_model_and_rounds_down_to_the_rack() -> None:
    assert load_for(Load(133.33, "total"), 8, 8, BAR) == Load(100, "total")
    assert load_for(Load(133.33, "total"), 5, 8, BAR) == Load(107.5, "total")
    assert load_for(Load(120, "total"), 1, 9, BAR) == Load(112.5, "total")
