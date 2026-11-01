import datetime

from support.exposures import an_exposure

from coach.core.goal import Milestone, Target
from coach.core.progress import milestone_read

HISTORY = (
    an_exposure("2026-09-01", (100, 5, 8)),
    an_exposure("2026-09-08", (105, 4, 9)),
    an_exposure("2026-09-15", (105, 5, 9), (100, 5, 8)),
    an_exposure("2026-09-22", (110, 5, 9)),
)


def day(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)


def test_a_load_x_reps_milestone_is_reached_by_the_first_exposure_meeting_load_and_reps() -> None:
    read = milestone_read(
        Milestone("bb_bench_press", Target("load_x_reps", load=105, reps=5)), HISTORY, {}, "kg"
    )

    assert (read.reached, read.to_go, read.computable) == (day("2026-09-15"), None, True)


def test_an_unreached_load_x_reps_milestone_shows_the_reps_to_go_at_its_load() -> None:
    read = milestone_read(
        Milestone("bb_bench_press", Target("load_x_reps", load=110, reps=8)), HISTORY, {}, "kg"
    )

    assert (read.reached, read.to_go) == (None, {"reps": 3})


def test_a_load_out_of_reach_shows_the_load_to_go_at_its_reps() -> None:
    read = milestone_read(
        Milestone("bb_bench_press", Target("load_x_reps", load=120, reps=5)), HISTORY, {}, "kg"
    )

    assert read.to_go == {"load": 10}


def test_an_e1rm_milestone_is_reached_on_the_first_exposure_whose_e1rm_meets_it() -> None:
    reached = milestone_read(Milestone("bb_bench_press", Target("e1rm", 125)), HISTORY, {}, "kg")
    short = milestone_read(Milestone("bb_bench_press", Target("e1rm", 140)), HISTORY, {}, "kg")

    assert reached.reached == day("2026-09-15")
    assert (short.reached, short.to_go) == (None, {"load": 8.0})


def test_a_bodyweight_multiple_with_one_weigh_in_in_14_days_is_not_computable() -> None:
    weigh_ins = {day("2026-09-20"): 80.0}

    read = milestone_read(
        Milestone("bb_bench_press", Target("bodyweight_multiple", 1.5)), HISTORY, weigh_ins, "kg"
    )

    assert (read.reached, read.to_go, read.computable) == (None, None, False)


def test_a_bodyweight_multiple_reads_the_14_day_average_on_the_exposures_date() -> None:
    weigh_ins = {day("2026-09-10"): 81.0, day("2026-09-20"): 79.0}

    reached = milestone_read(
        Milestone("bb_bench_press", Target("bodyweight_multiple", 1.6)), HISTORY, weigh_ins, "kg"
    )
    short = milestone_read(
        Milestone("bb_bench_press", Target("bodyweight_multiple", 2.0)), HISTORY, weigh_ins, "kg"
    )

    assert reached.reached == day("2026-09-22")
    assert (short.computable, short.to_go) == (True, {"multiple": 0.35})
