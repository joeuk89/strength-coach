from coach.core.exercise_ladder import RungShape, full_criterion, rung_shapes
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


def test_an_open_top_rep_out_reads_its_number() -> None:
    ladder = ExerciseLadder((Rung("push_up", (SetGroup(3, reps="8+", rpe=8),)),))

    assert full_criterion(ladder, 1) == Advance(reps=8, rpe_at_most=8, exposures=2)


def test_every_rung_takes_the_shape_program_show_and_the_pages_read() -> None:
    shapes = rung_shapes(
        ExerciseLadder(
            (
                Rung("negative_pull_up", (SetGroup(3, reps=(3, 5), rpe=8),), cues="slow"),
                Rung("pull_up", (SetGroup(3, reps=3, rpe=9),), advance=Advance(manual=True)),
            ),
            Advance(exposures=3),
        ),
        standing=2,
    )

    assert shapes == (
        RungShape(
            rung=1,
            exercise="negative_pull_up",
            name="negative_pull_up",
            cues="slow",
            set_groups=({"count": 3, "reps": [3, 5], "rpe": 8},),
            criterion={"reps": 5, "rpe_at_most": 8, "exposures": 3},
            standing=False,
        ),
        RungShape(
            rung=2,
            exercise="pull_up",
            name="pull_up",
            cues=None,
            set_groups=({"count": 3, "reps": 3, "rpe": 9},),
            criterion={"manual": True},
            standing=True,
        ),
    )


def test_a_rung_shape_says_its_exercise_by_the_name_it_is_given() -> None:
    names = {"negative_pull_up": "Negatives", "band_pull_up": "Band", "pull_up": "Pull-up"}

    [first, *_] = rung_shapes(LADDER, standing=1, name_of=names.__getitem__)

    assert (first.exercise, first.name) == ("negative_pull_up", "Negatives")
