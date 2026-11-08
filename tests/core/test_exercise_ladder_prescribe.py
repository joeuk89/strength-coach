import datetime
from typing import Any

from support.prescribe import a_request

from coach.core.exposure import Exposure, ExposureSet, Matched
from coach.core.flag import Flag
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    ExerciseFacts,
    LinePrescription,
    PlanOverride,
    Step,
)
from coach.core.program.form import (
    Advance,
    ExerciseLadder,
    Line,
    Rung,
    SchemeRef,
    SetGroup,
)

ADOPTED = datetime.date(2026, 10, 1)
BODYWEIGHT = ExerciseFacts("bodyweight", "bodyweight", "vertical_pull")
DURATION = ExerciseFacts("duration", "bodyweight", "balance")
EXERCISES = {
    "negative_pull_up": BODYWEIGHT,
    "band_pull_up": BODYWEIGHT,
    "pull_up": BODYWEIGHT,
    "board_stand": DURATION,
    "board_tilt": DURATION,
}
TWO_EXPOSURES = Advance(exposures=2)


def ladder_line(*rungs: Rung, advance: Advance = TWO_EXPOSURES) -> Line:
    return Line(
        exercise=rungs[0].exercise,
        sets=rungs[0].sets,
        rest_s=120,
        scheme=SchemeRef("exercise_ladder", {}, ExerciseLadder(rungs, advance)),
    )


PULL_UP_LADDER = ladder_line(
    Rung("negative_pull_up", (SetGroup(3, reps=5, rpe=8),), "five-second lowers"),
    Rung("band_pull_up", (SetGroup(3, reps=6, rpe=8),), "green band"),
    Rung("pull_up", (SetGroup(4, reps=3, rpe=8),), "dead hang to chin over"),
)


def ladder_rung(rung: int, on: str, exercise: str = "negative_pull_up") -> DecisionInForce:
    return DecisionInForce(
        id=f"d-{on}",
        kind="ladder_rung",
        session_id="lower",
        exercise_id=exercise,
        params={"rung": rung},
        on=datetime.date.fromisoformat(on),
    )


def logged(
    exercise: str, on: str, *sets: tuple[int, float | None], duration: bool = False
) -> Exposure:
    """Working sets of (reps, rpe), or of (seconds, rpe) with `duration`."""
    return Exposure(
        workout_id=f"w-{on}",
        exercise_id=exercise,
        date=datetime.date.fromisoformat(on),
        sets=tuple(
            ExposureSet(
                i,
                "working",
                None,
                None if duration else amount,
                rpe,
                duration_s=amount if duration else None,
            )
            for i, (amount, rpe) in enumerate(sets)
        ),
        match=Matched("lower"),
    )


def derive(
    line: Line = PULL_UP_LADDER,
    *exposures: Exposure,
    decisions: tuple[DecisionInForce, ...] = (),
    **request: Any,
) -> LinePrescription:
    built = a_request(
        line,
        exposures=exposures,
        exercises=EXERCISES,
        decisions=decisions,
        adopted=ADOPTED,
        **request,
    )
    return prescribe(built).lines[0]


def ladder_flags(line: LinePrescription) -> list[tuple[str, dict[str, object]]]:
    return [(f.code, dict(f.params)) for f in line.flags if f.code in ("rung_met", "ladder_top")]


def flag(line: LinePrescription, code: str) -> Flag:
    return next(f for f in line.flags if f.code == code)


def shape(line: LinePrescription) -> list[tuple[int, int | None, float | None]]:
    return [(g.count, g.reps if isinstance(g.reps, int) else None, g.rpe) for g in line.groups]


def negatives(on: str, rpe: float = 8) -> Exposure:
    return logged("negative_pull_up", on, (5, rpe), (5, 8), (5, 8))


def bands(on: str) -> Exposure:
    return logged("band_pull_up", on, (6, 8), (6, 7), (6, 8))


def pull_ups(on: str, reps: int = 3) -> Exposure:
    return logged("pull_up", on, (reps, 8), (reps, 8), (reps, 8), (reps, 8))


def test_with_no_ladder_rung_decision_the_line_stands_on_the_first_rung() -> None:
    line = derive()

    assert line.exercise_id == "negative_pull_up"
    assert shape(line) == [(3, 5, 8)]


def test_a_ladder_rung_decision_naming_rung_3_prescribes_rung_3s_exercise_and_sets() -> None:
    line = derive(decisions=(ladder_rung(3, "2026-10-20"),))

    assert line.exercise_id == "pull_up"
    assert shape(line) == [(4, 3, 8)]


def test_line_flags_keep_the_lines_key_whichever_rung_it_stands_on() -> None:
    line = derive(
        PULL_UP_LADDER,
        bands("2026-10-22"),
        bands("2026-10-29"),
        decisions=(ladder_rung(2, "2026-10-20"),),
    )

    assert flag(line, "rung_met").scope.exercise_id == "negative_pull_up"


def test_two_exposures_meeting_the_criterion_raise_rung_met_naming_the_next_rung() -> None:
    line = derive(PULL_UP_LADDER, negatives("2026-10-19"), negatives("2026-10-26"))

    assert ladder_flags(line) == [
        (
            "rung_met",
            {
                "rung": 1,
                "next": "band_pull_up",
                "exposures": [
                    "exposure:w-2026-10-19/negative_pull_up",
                    "exposure:w-2026-10-26/negative_pull_up",
                ],
            },
        )
    ]
    assert flag(line, "rung_met").rn == "rn:bodyweight-skill-progression.3"


def test_one_exposure_meeting_the_criterion_raises_nothing() -> None:
    assert ladder_flags(derive(PULL_UP_LADDER, negatives("2026-10-26"))) == []


def test_two_exposures_with_one_over_the_rpe_raise_nothing() -> None:
    line = derive(PULL_UP_LADDER, negatives("2026-10-19", rpe=9), negatives("2026-10-26"))

    assert ladder_flags(line) == []


def test_two_exposures_with_a_set_short_of_the_reps_raise_nothing() -> None:
    short = logged("negative_pull_up", "2026-10-26", (5, 8), (4, 8), (5, 8))

    assert ladder_flags(derive(PULL_UP_LADDER, negatives("2026-10-19"), short)) == []


def test_exposures_dated_before_the_ladder_rung_decision_do_not_count() -> None:
    line = derive(
        PULL_UP_LADDER,
        bands("2026-10-12"),
        bands("2026-10-19"),
        bands("2026-10-26"),
        decisions=(ladder_rung(2, "2026-10-20"),),
    )

    assert ladder_flags(line) == []


def test_rung_1s_window_opens_at_the_versions_adoption() -> None:
    line = derive(PULL_UP_LADDER, negatives("2026-09-28"), negatives("2026-10-26"))

    assert ladder_flags(line) == []


def test_exposures_on_another_rungs_exercise_count_for_nothing() -> None:
    line = derive(
        PULL_UP_LADDER,
        negatives("2026-10-22"),
        negatives("2026-10-29"),
        decisions=(ladder_rung(2, "2026-10-20"),),
    )

    assert ladder_flags(line) == []


def test_the_criterion_met_on_the_last_rung_raises_ladder_top_not_rung_met() -> None:
    line = derive(
        PULL_UP_LADDER,
        pull_ups("2026-10-22"),
        pull_ups("2026-10-29"),
        decisions=(ladder_rung(3, "2026-10-20"),),
    )

    assert ladder_flags(line) == [("ladder_top", {"rung": 3})]
    assert flag(line, "ladder_top").rn == "rn:bodyweight-skill-progression.3"


def test_a_manual_rung_raises_neither() -> None:
    manual = ladder_line(
        Rung("negative_pull_up", (SetGroup(3, reps=5, rpe=8),), advance=Advance(manual=True)),
        Rung("band_pull_up", (SetGroup(3, reps=6, rpe=8),)),
    )

    assert ladder_flags(derive(manual, negatives("2026-10-19"), negatives("2026-10-26"))) == []


def test_a_rung_asking_for_three_exposures_needs_three() -> None:
    three = ladder_line(
        Rung("negative_pull_up", (SetGroup(3, reps=5, rpe=8),), advance=Advance(exposures=3)),
        Rung("band_pull_up", (SetGroup(3, reps=6, rpe=8),)),
    )
    two = (negatives("2026-10-19"), negatives("2026-10-26"))

    assert ladder_flags(derive(three, *two)) == []
    assert [code for code, _ in ladder_flags(derive(three, negatives("2026-10-12"), *two))] == [
        "rung_met"
    ]


def test_a_duration_rung_reads_the_logged_seconds() -> None:
    board = ladder_line(
        Rung("board_stand", (SetGroup(2, duration_s=30, rpe=5),)),
        Rung("board_tilt", (SetGroup(2, duration_s=60, rpe=6),)),
    )
    held = logged("board_stand", "2026-10-26", (30, 5), (32, 4), duration=True)
    shaky = logged("board_stand", "2026-10-19", (30, 5), (25, 5), duration=True)
    clean = logged("board_stand", "2026-10-19", (30, 5), (30, 5), duration=True)

    assert ladder_flags(derive(board, shaky, held)) == []
    assert [code for code, _ in ladder_flags(derive(board, clean, held))] == ["rung_met"]


def test_rung_mets_hash_holds_through_a_third_qualifying_exposure_and_moves_with_the_rung() -> None:
    two = derive(PULL_UP_LADDER, negatives("2026-10-12"), negatives("2026-10-19"))
    three = derive(
        PULL_UP_LADDER, negatives("2026-10-12"), negatives("2026-10-19"), negatives("2026-10-26")
    )
    moved = derive(
        PULL_UP_LADDER,
        bands("2026-10-22"),
        bands("2026-10-29"),
        decisions=(ladder_rung(2, "2026-10-20"),),
    )

    assert flag(two, "rung_met").params != flag(three, "rung_met").params
    assert flag(two, "rung_met").params_hash == flag(three, "rung_met").params_hash
    assert flag(two, "rung_met").key == flag(moved, "rung_met").key
    assert flag(moved, "rung_met").params_hash != flag(two, "rung_met").params_hash


def test_a_return_band_of_22_to_42_days_prescribes_two_rungs_back_with_the_bands_cut() -> None:
    line = derive(
        PULL_UP_LADDER,
        pull_ups("2026-10-08"),
        decisions=(ladder_rung(3, "2026-10-01"),),
    )

    assert line.exercise_id == "negative_pull_up"
    assert [(g.count, g.reps, g.rpe_cap) for g in line.groups] == [(2, 5, 8)]
    assert line.steps[0] == Step("cut", "pull_up", "negative_pull_up", "return 22–42, 25 days off")


def test_after_the_return_week_the_line_stands_on_its_rung_again() -> None:
    line = derive(
        PULL_UP_LADDER,
        pull_ups("2026-10-08"),
        negatives("2026-10-26"),
        decisions=(ladder_rung(3, "2026-10-01"),),
    )

    assert line.exercise_id == "pull_up"
    assert shape(line) == [(4, 3, 8)]


def test_a_light_week_holds_the_rung_and_cuts_its_sets() -> None:
    line = derive(
        PULL_UP_LADDER,
        decisions=(ladder_rung(3, "2026-10-20"),),
        overrides=(PlanOverride("light_week"),),
    )

    assert line.exercise_id == "pull_up"
    assert [(g.count, g.reps, g.rpe_cap) for g in line.groups] == [(2, 3, 8)]


def test_stall_streak_reads_only_exposures_since_the_standing_rungs_start() -> None:
    flat = (pull_ups("2026-10-15"), pull_ups("2026-10-22", 2), pull_ups("2026-10-29", 2))

    since_before = derive(PULL_UP_LADDER, *flat, decisions=(ladder_rung(3, "2026-10-10"),))
    since_between = derive(PULL_UP_LADDER, *flat, decisions=(ladder_rung(3, "2026-10-20"),))

    assert [f.code for f in since_before.flags] == ["stall_streak"]
    assert [f.code for f in since_between.flags] == []


def test_a_practice_ladder_held_at_target_for_three_exposures_raises_no_stall_streak() -> None:
    held = (negatives("2026-10-12"), negatives("2026-10-19"), negatives("2026-10-26"))

    assert "stall_streak" not in [
        f.code for f in derive(PULL_UP_LADDER, *held, kind="practice").flags
    ]


def test_a_lifting_ladder_with_the_same_exposures_still_raises_stall_streak() -> None:
    held = (negatives("2026-10-12"), negatives("2026-10-19"), negatives("2026-10-26"))

    assert "stall_streak" in [f.code for f in derive(PULL_UP_LADDER, *held).flags]


def test_a_practice_ladder_still_raises_rung_met() -> None:
    held = (negatives("2026-10-19"), negatives("2026-10-26"))

    assert [code for code, _ in ladder_flags(derive(PULL_UP_LADDER, *held, kind="practice"))] == [
        "rung_met"
    ]
