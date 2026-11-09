from coach.core.program.form import ExerciseLadder, Line, Rung, SchemeRef, SetGroup

SETS = (SetGroup(3, reps=8, rpe=8),)


def a_line(scheme: SchemeRef) -> Line:
    return Line("dead_bug", SETS, 60, scheme)


def a_ladder_of(*exercises: str) -> ExerciseLadder:
    return ExerciseLadder(tuple(Rung(exercise, SETS) for exercise in exercises))


def test_a_ladder_line_names_its_ladder_and_its_rung_exercises_in_rung_order() -> None:
    ladder = a_ladder_of("dead_bug", "ab_wheel", "hanging_leg_raise")

    line = a_line(SchemeRef("exercise_ladder", ladder=ladder))

    assert line.ladder == ladder
    assert line.rung_exercises == ("dead_bug", "ab_wheel", "hanging_leg_raise")


def test_rung_exercises_keeps_one_entry_per_rung_when_an_exercise_repeats() -> None:
    ladder = a_ladder_of("dead_bug", "dead_bug", "ab_wheel")

    line = a_line(SchemeRef("exercise_ladder", ladder=ladder))

    assert line.rung_exercises == ("dead_bug", "dead_bug", "ab_wheel")


def test_a_line_with_no_ladder_has_no_rung_exercises() -> None:
    line = a_line(SchemeRef("double_progression"))

    assert line.ladder is None
    assert line.rung_exercises == ()
