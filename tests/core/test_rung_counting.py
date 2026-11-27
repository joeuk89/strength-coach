import datetime
from typing import Any

from support.prescribe import a_rack, a_request

from coach.core.exposure import Exposure, ExposureSet, Matched
from coach.core.load import Load, LoadMode
from coach.core.prescribe import prescribe
from coach.core.prescription import DecisionInForce, ExerciseFacts, LinePrescription
from coach.core.program.form import Advance, ExerciseLadder, Line, Rung, SchemeRef, SetGroup

ADOPTED = datetime.date(2026, 8, 1)
CLIMBED = datetime.date(2026, 9, 1)
NEGATIVE = "weighted_negative"
EXERCISES = {
    NEGATIVE: ExerciseFacts("total", "vest", "vertical_pull"),
    "db_negative": ExerciseFacts("per_hand_x2", "dumbbell", "vertical_pull"),
    "pull_up": ExerciseFacts("bodyweight", "bodyweight", "vertical_pull"),
    "chin_up": ExerciseFacts("bodyweight", "bodyweight", "vertical_pull"),
}
RACKS = {"vest": a_rack(5, 10, 15, 20, 25, 30), "dumbbell": a_rack(10, 20, 30)}
SETS = (SetGroup(3, reps=4, rpe=8),)


def a_ladder(*rungs: Rung, **line: Any) -> Line:
    return Line(
        exercise=rungs[0].exercise,
        sets=rungs[0].sets,
        rest_s=120,
        scheme=SchemeRef("exercise_ladder", {}, ExerciseLadder(rungs, Advance(exposures=2))),
        **line,
    )


THREE_LOADED = a_ladder(
    Rung(NEGATIVE, SETS, "lower for 4 s"),
    Rung(NEGATIVE, SETS, "lower for 8 s", start_load=20),
    Rung(NEGATIVE, SETS, "lower for 10 s", start_load=30),
    start_load=10,
)


def standing_on(rung: int, on: datetime.date = CLIMBED, line: str = NEGATIVE) -> DecisionInForce:
    return DecisionInForce(
        id=f"d-{on}",
        kind="ladder_rung",
        session_id="lower",
        exercise_id=line,
        params={"rung": rung},
        on=on,
    )


def logged(
    on: str,
    load: float | None,
    *,
    exercise: str = NEGATIVE,
    returned: bool = False,
    reps: int = 4,
    mode: LoadMode = "total",
) -> Exposure:
    return Exposure(
        workout_id=f"w-{on}",
        exercise_id=exercise,
        date=datetime.date.fromisoformat(on),
        sets=tuple(
            ExposureSet(i, "working", None if load is None else Load(load, mode), reps, 8)
            for i in range(3)
        ),
        match=Matched("lower", return_band_lines=frozenset({exercise} if returned else ())),
    )


def derive(
    line: Line, *exposures: Exposure, decisions: tuple[DecisionInForce, ...]
) -> LinePrescription:
    built = a_request(
        line,
        exposures=exposures,
        exercises=EXERCISES,
        decisions=decisions,
        adopted=ADOPTED,
        racks=RACKS,
    )
    return prescribe(built).lines[0]


def working_load(line: LinePrescription) -> float | None:
    [load] = {None if g.load is None else g.load.amount for g in line.groups if g.type == "working"}
    return load


ON_RUNG_THREE = (logged("2026-09-05", 30), logged("2026-09-08", 30))


def test_back_on_the_rung_after_a_step_back_week_the_rung_holds_its_pre_layoff_load() -> None:
    stepped_back = logged("2026-10-27", 10, returned=True)

    line = derive(THREE_LOADED, *ON_RUNG_THREE, stepped_back, decisions=(standing_on(3),))

    assert line.rung == 3
    assert working_load(line) == 30
    assert line.derived_from == "exposure:w-2026-09-08/weighted_negative"


def test_in_the_step_back_week_the_first_rung_opens_on_its_own_start_load() -> None:
    line = derive(THREE_LOADED, *ON_RUNG_THREE, decisions=(standing_on(3),))

    assert line.rung == 1
    assert line.derived_from == "start_load"
    assert working_load(line) == 5


def test_a_decision_back_to_a_loaded_first_rung_ignores_a_log_from_before_the_move() -> None:
    ladder = a_ladder(Rung(NEGATIVE, SETS), Rung("chin_up", SETS), start_load=10)
    before_the_move = logged("2026-10-29", 20)

    line = derive(ladder, before_the_move, decisions=(standing_on(1, datetime.date(2026, 10, 30)),))

    assert line.rung == 1
    assert line.derived_from == "start_load"
    assert working_load(line) == 10


def test_after_a_decision_back_to_the_first_rung_its_own_log_holds() -> None:
    ladder = a_ladder(Rung(NEGATIVE, SETS), Rung("chin_up", SETS), start_load=10)

    line = derive(
        ladder,
        logged("2026-10-29", 20),
        logged("2026-10-31", 15),
        decisions=(standing_on(1, datetime.date(2026, 10, 30)),),
    )

    assert working_load(line) == 15


def test_a_rung_on_the_lines_exercise_prescribes_in_the_lines_load_mode() -> None:
    ladder = a_ladder(
        Rung("db_negative", SETS, "lower for 4 s"),
        Rung("db_negative", SETS, "lower for 8 s", start_load=30),
        start_load=10,
        load_mode="total",
    )

    line = derive(ladder, decisions=(standing_on(2, line="db_negative"),))

    assert line.groups[0].load == Load(30, "total")


TEMPO = a_ladder(
    Rung("pull_up", SETS, "lower for 4 s"),
    Rung("pull_up", SETS, "lower for 8 s"),
    Rung("pull_up", SETS, "lower for 10 s"),
)


def test_a_step_back_log_does_not_count_toward_the_standing_rungs_criterion() -> None:
    stepped_back = logged("2026-10-20", None, exercise="pull_up", returned=True)
    back_on_the_rung = logged("2026-10-27", None, exercise="pull_up")

    line = derive(
        TEMPO, stepped_back, back_on_the_rung, decisions=(standing_on(2, line="pull_up"),)
    )

    assert line.rung == 2
    assert "rung_met" not in [f.code for f in line.flags]


def test_two_clean_logs_on_the_standing_rung_meet_its_criterion() -> None:
    clean = (
        logged("2026-10-20", None, exercise="pull_up"),
        logged("2026-10-27", None, exercise="pull_up"),
    )

    line = derive(TEMPO, *clean, decisions=(standing_on(2, line="pull_up"),))

    assert "rung_met" in [f.code for f in line.flags]


def test_a_loaded_rung_on_its_own_exercise_still_holds_its_own_log_after_a_step_back() -> None:
    ladder = a_ladder(Rung("pull_up", SETS), Rung(NEGATIVE, SETS, "vest on", start_load=10))
    stepped_back = logged("2026-10-27", None, exercise="pull_up", returned=True)

    line = derive(
        ladder, logged("2026-09-08", 15), stepped_back, decisions=(standing_on(2, line="pull_up"),)
    )

    assert line.rung == 2
    assert working_load(line) == 15
    assert line.groups[0].load == Load(15, "total")
