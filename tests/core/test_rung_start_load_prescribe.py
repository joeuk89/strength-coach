import datetime
from dataclasses import replace
from typing import Any

from support.prescribe import a_rack, a_request

from coach.core.exposure import Exposure, ExposureSet, Matched
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    DecisionInForce,
    ExerciseFacts,
    LinePrescription,
    PlanOverride,
)
from coach.core.program.form import Advance, ExerciseLadder, Line, Rung, SchemeRef, SetGroup

ADOPTED = datetime.date(2026, 10, 1)
RUNG_START = datetime.date(2026, 10, 25)
EXERCISES = {
    "negative_pull_up": ExerciseFacts("bodyweight", "bodyweight", "vertical_pull"),
    "chin_up": ExerciseFacts("bodyweight", "bodyweight", "vertical_pull"),
    "weighted_negative": ExerciseFacts("total", "vest", "vertical_pull"),
    "db_negative": ExerciseFacts("per_hand_x2", "dumbbell", "vertical_pull"),
    "goblet_squat": ExerciseFacts("single_implement", "dumbbell", "squat"),
}
RACKS = {"vest": a_rack(5, 10, 15, 20), "dumbbell": a_rack(10, 20, 30)}
SETS = (SetGroup(3, reps=4, rpe=8),)


def a_ladder(*rungs: Rung, **line: Any) -> Line:
    return Line(
        exercise=rungs[0].exercise,
        sets=rungs[0].sets,
        rest_s=120,
        scheme=SchemeRef("exercise_ladder", {}, ExerciseLadder(rungs, Advance(exposures=2))),
        **line,
    )


LADDER = a_ladder(
    Rung("negative_pull_up", SETS, "lower for 4 s"),
    Rung("weighted_negative", SETS, "vest on", start_load=5),
)


def standing_on(rung: int, on: datetime.date = RUNG_START) -> DecisionInForce:
    return DecisionInForce(
        id=f"d-{on}",
        kind="ladder_rung",
        session_id="lower",
        exercise_id="negative_pull_up",
        params={"rung": rung},
        on=on,
    )


def logged(
    on: str,
    load: float,
    exercise: str = "weighted_negative",
    session: str | None = "lower",
) -> Exposure:
    return Exposure(
        workout_id=f"w-{on}-{session}",
        exercise_id=exercise,
        date=datetime.date.fromisoformat(on),
        sets=tuple(ExposureSet(i, "working", Load(load, "total"), 4, 8) for i in range(3)),
        match=None if session is None else Matched(session),
    )


def derive(
    line: Line = LADDER,
    *exposures: Exposure,
    decisions: tuple[DecisionInForce, ...] = (standing_on(2),),
    **request: Any,
) -> LinePrescription:
    built = a_request(
        line,
        exposures=exposures,
        exercises=EXERCISES,
        decisions=decisions,
        adopted=ADOPTED,
        racks=RACKS,
        **request,
    )
    return prescribe(built).lines[0]


def working_load(line: LinePrescription) -> float | None:
    [load] = {None if g.load is None else g.load.amount for g in line.groups if g.type == "working"}
    return load


def codes(line: LinePrescription) -> list[str]:
    return [f.code for f in line.flags]


def test_standing_on_a_loaded_rung_with_no_exposure_prescribes_its_load_and_raises_nothing() -> (
    None
):
    line = derive()

    assert line.exercise_id == "weighted_negative"
    assert working_load(line) == 5
    assert line.derived_from == "start_load"
    assert line.change == "first prescription"
    assert line.flags == ()


def test_exposures_before_the_rungs_start_do_not_anchor_it() -> None:
    line = derive(LADDER, logged("2026-10-23", 20), logged("2026-10-24", 15))

    assert working_load(line) == 5
    assert line.derived_from == "start_load"


def test_a_shared_exercises_earlier_exposures_at_another_load_do_not_anchor_the_rung() -> None:
    shared = a_ladder(
        Rung("db_negative", SETS, "lower for 4 s"),
        Rung("db_negative", SETS, "lower for 8 s", start_load=20),
        start_load=10,
    )
    earlier = Exposure(
        workout_id="w-1",
        exercise_id="db_negative",
        date=datetime.date(2026, 10, 23),
        sets=tuple(ExposureSet(i, "working", Load(30, "per_hand_x2"), 4, 8) for i in range(3)),
        match=Matched("lower"),
    )

    line = derive(
        shared,
        earlier,
        decisions=(replace(standing_on(2), exercise_id="db_negative"),),
    )

    assert working_load(line) == 20
    assert line.derived_from == "start_load"
    assert line.groups[0].load == Load(20, "per_hand_x2")


def test_a_shared_exercises_log_on_the_rungs_start_date_belongs_to_the_previous_rung() -> None:
    shared = a_ladder(
        Rung("db_negative", SETS, "lower for 4 s"),
        Rung("db_negative", SETS, "lower for 8 s", start_load=20),
        start_load=10,
    )
    earned_the_climb = Exposure(
        workout_id="w-1",
        exercise_id="db_negative",
        date=RUNG_START,
        sets=tuple(ExposureSet(i, "working", Load(10, "per_hand_x2"), 4, 8) for i in range(3)),
        match=Matched("lower"),
    )

    line = derive(
        shared,
        earned_the_climb,
        decisions=(replace(standing_on(2), exercise_id="db_negative"),),
    )

    assert line.groups[0].load == Load(20, "per_hand_x2")
    assert line.derived_from == "start_load"
    assert line.change == "first prescription"


def test_a_log_on_the_rungs_start_date_still_counts_toward_its_criterion() -> None:
    top = a_ladder(
        Rung("negative_pull_up", SETS),
        Rung("weighted_negative", SETS, start_load=5),
        Rung("chin_up", SETS),
    )

    line = derive(top, logged("2026-10-25", 5), logged("2026-10-27", 5))

    assert "rung_met" in codes(line)


def test_another_sessions_exposures_since_the_rungs_start_do_not_anchor_it() -> None:
    line = derive(LADDER, logged("2026-10-27", 20, session="upper"))

    assert working_load(line) == 5


def test_a_second_exposure_holds_the_load_logged_on_the_first() -> None:
    line = derive(LADDER, logged("2026-10-27", 5))

    assert working_load(line) == 5
    assert line.derived_from == "exposure:w-2026-10-27-lower/weighted_negative"
    assert line.change == "held"


def test_a_met_rung_never_steps_its_load_up() -> None:
    top = a_ladder(
        Rung("negative_pull_up", SETS),
        Rung("weighted_negative", SETS, start_load=5),
        Rung("chin_up", SETS),
    )

    line = derive(top, logged("2026-10-27", 5), logged("2026-10-30", 5))

    assert working_load(line) == 5
    assert "rung_met" in codes(line)


def test_history_since_the_start_wins_when_the_athlete_logged_another_row() -> None:
    line = derive(LADDER, logged("2026-10-23", 20), logged("2026-10-27", 10))

    assert working_load(line) == 10


def test_an_unmatched_workout_since_the_start_counts_on_the_rung() -> None:
    line = derive(LADDER, logged("2026-10-27", 10, session=None))

    assert working_load(line) == 10


def test_a_rung_stepped_back_to_opens_on_its_own_load() -> None:
    three = a_ladder(
        Rung("negative_pull_up", SETS),
        Rung("weighted_negative", SETS, "vest on", start_load=10),
        Rung("weighted_negative", (SetGroup(4, reps=4, rpe=8),), "more sets", start_load=20),
    )

    line = derive(
        three,
        logged("2026-10-15", 20),
        decisions=(standing_on(3, datetime.date(2026, 10, 1)),),
    )

    assert line.rung == 2
    assert line.exercise_id == "weighted_negative"
    assert line.derived_from == "start_load"
    assert next(s.cause for s in line.steps if s.step == "cut").startswith("return")
    assert working_load(line) == 5


def test_a_swap_reads_the_swapped_exercises_own_history_and_load() -> None:
    swap = PlanOverride(
        "swap_exercise",
        "lower",
        "negative_pull_up",
        params={"to": "goblet_squat", "start_load": 20},
    )
    history = Exposure(
        workout_id="w-1",
        exercise_id="goblet_squat",
        date=datetime.date(2026, 10, 30),
        sets=tuple(ExposureSet(i, "working", Load(30, "single_implement"), 4, 8) for i in range(3)),
        match=Matched("lower"),
    )

    line = derive(LADDER, history, overrides=(swap,))

    assert line.exercise_id == "goblet_squat"
    assert line.derived_from == "exposure:w-1/goblet_squat"


def test_a_loaded_rung_from_an_older_version_with_no_load_keeps_the_old_search() -> None:
    stale = a_ladder(Rung("negative_pull_up", SETS), Rung("weighted_negative", SETS))

    assert codes(derive(stale)) == ["start_load_missing"]
    assert working_load(derive(stale, logged("2026-10-23", 15))) == 15


def test_a_later_rung_reads_its_exercises_mode_not_the_lines() -> None:
    line_mode = a_ladder(
        Rung("goblet_squat", SETS),
        Rung("db_negative", SETS, start_load=20),
        load_mode="total",
        start_load=20,
    )

    line = derive(line_mode, decisions=(replace(standing_on(2), exercise_id="goblet_squat"),))

    assert line.groups[0].load == Load(20, "per_hand_x2")


def test_the_first_rung_still_reads_the_lines_start_load_and_history() -> None:
    first = a_ladder(
        Rung("weighted_negative", SETS),
        Rung("chin_up", SETS),
        start_load=10,
    )

    assert working_load(derive(first, decisions=())) == 10
    assert working_load(derive(first, logged("2026-10-30", 15), decisions=())) == 15
