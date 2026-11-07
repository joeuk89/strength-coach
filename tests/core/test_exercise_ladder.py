from coach.core.exercise_ladder import full_criterion
from coach.core.program.form import Advance, ExerciseLadder, Rung, SetGroup

LADDER = ExerciseLadder(
    (
        Rung("negative_pull_up", (SetGroup(3, reps=(3, 5), rpe=8),)),
        Rung("band_pull_up", (SetGroup(3, reps=6, rpe=8),), advance=Advance(rpe_at_most=7)),
        Rung("pull_up", (SetGroup(3, reps=3, rpe=9),), advance=Advance(manual=True)),
    ),
    Advance(exposures=3),
)


def test_a_reps_rung_reads_the_top_of_its_range_at_its_rpe() -> None:
    assert full_criterion(LADDER, 1) == Advance(reps=5, rpe_at_most=8, exposures=3)


def test_a_rung_key_overrides_what_its_group_would_say() -> None:
    assert full_criterion(LADDER, 2) == Advance(reps=6, rpe_at_most=7, exposures=3)


def test_a_manual_rung_reads_nothing_from_the_logs() -> None:
    assert full_criterion(LADDER, 3) == Advance(manual=True)


def test_with_nothing_said_the_run_is_two_exposures() -> None:
    ladder = ExerciseLadder((Rung("plank", (SetGroup(2, duration_s=30, rpe=6),)),))

    assert full_criterion(ladder, 1) == Advance(duration_s=30, rpe_at_most=6, exposures=2)
