import datetime

from coach.core.exercise_ladder import (
    LineRef,
    RungShape,
    StandingRung,
    full_criterion,
    ladder_read,
    rung_shapes,
    standing_rung,
)
from coach.core.flag import Scope
from coach.core.prescription import DecisionInForce, RungNaming
from coach.core.program.form import Advance, ExerciseLadder, Line, Rung, SchemeRef, SetGroup

LADDER = ExerciseLadder(
    (
        Rung("negative_pull_up", (SetGroup(3, reps=(3, 5), rpe=8),)),
        Rung("band_pull_up", (SetGroup(3, reps=6, rpe=8),), advance=Advance(rpe_at_most=7)),
        Rung("pull_up", (SetGroup(3, reps=3, rpe=9),), advance=Advance(manual=True)),
    ),
    Advance(exposures=3),
)


NAMING = RungNaming("kg", {"negative_pull_up": "Negatives", "pull_up": "Pull-up"})


def a_ladder_line(ladder: ExerciseLadder) -> Line:
    return Line(ladder.rungs[0].exercise, (), 120, SchemeRef("exercise_ladder", {}, ladder))


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
    ladder = ExerciseLadder(
        (
            Rung("negative_pull_up", (SetGroup(3, reps=(3, 5), rpe=8),), cues="slow"),
            Rung("pull_up", (SetGroup(3, reps=3, rpe=9),), advance=Advance(manual=True)),
        ),
        Advance(exposures=3),
    )

    shapes = rung_shapes(a_ladder_line(ladder), ladder, 2, naming=NAMING)

    assert shapes == (
        RungShape(
            rung=1,
            exercise="negative_pull_up",
            label="rung 1 · Negatives · 3×3–5 @8 · slow",
            cues="slow",
            set_groups=({"count": 3, "reps": [3, 5], "rpe": 8},),
            criterion={"reps": 5, "rpe_at_most": 8, "exposures": 3},
            standing=False,
        ),
        RungShape(
            rung=2,
            exercise="pull_up",
            label="rung 2 · 3×3 @9",
            cues=None,
            set_groups=({"count": 3, "reps": 3, "rpe": 9},),
            criterion={"manual": True},
            standing=True,
        ),
    )


def a_rung_decision(session_id: str, line_key: str, rung: int) -> DecisionInForce:
    return DecisionInForce(
        f"d-{session_id}-{line_key}",
        "ladder_rung",
        session_id=session_id,
        exercise_id=line_key,
        params={"rung": rung},
        on=datetime.date(2026, 11, 2),
    )


def test_a_line_stands_on_the_decision_that_names_its_session_and_its_key() -> None:
    decisions = (
        a_rung_decision("upper", "negative_pull_up", 3),
        a_rung_decision("lower", "dead_bug", 3),
        a_rung_decision("lower", "negative_pull_up", 2),
    )

    standing = standing_rung(
        decisions, LADDER, line=LineRef("lower", "negative_pull_up"), adopted=None
    )

    assert standing == StandingRung(2, datetime.date(2026, 11, 2))


def test_a_line_no_decision_names_stands_on_the_opening_rung_from_its_adoption() -> None:
    adopted = datetime.date(2026, 10, 30)
    decisions = (a_rung_decision("upper", "negative_pull_up", 3),)

    standing = standing_rung(
        decisions, LADDER, line=LineRef("lower", "negative_pull_up"), adopted=adopted
    )

    assert standing == StandingRung(1, adopted)


def test_a_ladder_read_names_the_line_its_scope_names() -> None:
    read = ladder_read(
        a_ladder_line(LADDER),
        LADDER,
        StandingRung(1, None),
        (),
        scope=Scope("line", session_id="lower", exercise_id="negative_pull_up"),
        before=datetime.date(2026, 11, 2),
        acknowledgements=(),
        naming=NAMING,
    )

    assert read.line == LineRef("lower", "negative_pull_up")
