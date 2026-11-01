import datetime
from collections.abc import Mapping

from support.exposures import an_exposure
from support.prescribe import PLANNED, a_line, a_rack, a_request, working

from coach.core.exposure import Exposure
from coach.core.load import Load
from coach.core.prescribe import prescribe
from coach.core.prescription import (
    ConditioningDose,
    ExerciseFacts,
    MatchedActivity,
    PlannedSession,
    PrescribeRequest,
    ProgramVersion,
)
from coach.core.program.form import Line, ProgramForm, Schedule, SchemeRef, Session

LINES = (
    a_line("burpee", working(1, 10, None), scheme="hold"),
    a_line("air_squat", working(1, 15, None), scheme="hold"),
)
EXERCISES = {
    "burpee": ExerciseFacts("bodyweight", "bodyweight", "squat"),
    "air_squat": ExerciseFacts("bodyweight", "bodyweight", "squat"),
}
EMOM = SchemeRef(
    "emom_density",
    {
        "minutes": 10,
        "minutes_cap": 14,
        "minutes_step": 2,
        "reps": {"burpee": 10, "air_squat": 15},
        "reps_cap": {"burpee": 12, "air_squat": 20},
        "rpe_target": 8,
    },
)
CIRCUIT = SchemeRef(
    "circuit_rounds",
    {
        "rounds": 3,
        "rounds_cap": 5,
        "time_cap_minutes": 20,
        "reps": {"burpee": 10, "air_squat": 15},
        "rpe_target": 8,
    },
)
LAST_WEEK = datetime.date(2026, 10, 28)


def dose(scheme: SchemeRef, activity: MatchedActivity | None = None) -> ConditioningDose | None:
    session = Session("engine", "Engine", "conditioning", "optional", scheme=scheme, lines=LINES)
    form = ProgramForm(
        name="Test",
        kind="redesign",
        because="first program",
        emphasis="hypertrophy",
        location="home",
        schedule=Schedule(("A",), {"A": {"wed": "engine"}}),
        sessions=(session,),
    )
    request = PrescribeRequest(
        version=ProgramVersion(form, EXERCISES),
        exposures=(),
        racks={},
        planned=PlannedSession("engine", PLANNED, "home", "conditioning", LINES),
        activities={} if activity is None else {"engine": activity},
    )
    return prescribe(request).dose


def did(
    minutes: int, rpe: float, reps: Mapping[str, int] | None = None, rounds: int | None = None
) -> MatchedActivity:
    return MatchedActivity(LAST_WEEK, minutes, rpe, reps or {"burpee": 10, "air_squat": 15}, rounds)


def shape(found: ConditioningDose | None) -> tuple[int | None, int | None, dict[str, int], str]:
    assert found is not None
    return found.minutes, found.rounds, dict(found.reps), found.change


def test_with_no_activity_the_params_stand_as_authored() -> None:
    assert shape(dose(EMOM)) == (10, None, {"burpee": 10, "air_squat": 15}, "as authored")


def test_an_emom_at_or_under_its_rpe_target_steps_the_minutes() -> None:
    assert shape(dose(EMOM, did(10, 8))) == (
        12,
        None,
        {"burpee": 10, "air_squat": 15},
        "10 → 12 min",
    )


def test_the_minutes_stop_at_the_cap() -> None:
    assert shape(dose(EMOM, did(13, 7)))[0] == 14


def test_at_the_minutes_cap_the_reps_step_by_one_up_to_their_cap() -> None:
    found = dose(EMOM, did(14, 7, {"burpee": 11, "air_squat": 20}))

    assert shape(found) == (14, None, {"burpee": 12, "air_squat": 20}, "reps +1")


def test_at_both_caps_the_dose_holds() -> None:
    found = dose(EMOM, did(14, 7, {"burpee": 12, "air_squat": 20}))

    assert shape(found)[3] == "held"


def test_over_the_rpe_target_the_dose_holds() -> None:
    assert shape(dose(EMOM, did(12, 9))) == (12, None, {"burpee": 10, "air_squat": 15}, "held")


def test_circuit_rounds_step_one_round_to_the_cap_then_reps() -> None:
    assert shape(dose(CIRCUIT, did(20, 7, rounds=3)))[1:] == (
        4,
        {"burpee": 10, "air_squat": 15},
        "3 → 4 rounds",
    )
    assert shape(dose(CIRCUIT, did(20, 7, rounds=5)))[1:] == (
        5,
        {"burpee": 11, "air_squat": 16},
        "reps +1",
    )


def test_a_lifting_session_carries_no_dose() -> None:
    assert prescribe(a_request()).dose is None


def a_conditioning_request(line: Line, *exposures: Exposure) -> PrescribeRequest:
    session = Session("engine", "Engine", "conditioning", "optional", scheme=EMOM, lines=(line,))
    form = ProgramForm(
        name="Test",
        kind="redesign",
        because="first program",
        emphasis="hypertrophy",
        location="home",
        schedule=Schedule(("A",), {"A": {"wed": "engine"}}),
        sessions=(session,),
    )
    return PrescribeRequest(
        version=ProgramVersion(form, {"bb_bench_press": EXERCISES_BENCH}),
        exposures=exposures,
        racks={"home": {"barbell": a_rack(100, 105, 107.5, 110, 115, 120, 125)}},
        planned=PlannedSession("engine", PLANNED, "home", "conditioning", (line,)),
    )


EXERCISES_BENCH = ExerciseFacts("total", "barbell", "horizontal_push")
BENCH = a_line("bb_bench_press", working(4, 5), scheme="linear")


def test_a_conditioning_line_authored_with_linear_holds_at_the_anchor_after_a_hit() -> None:
    hit = an_exposure("2026-10-28", (120, 5, 8), (120, 5, 8), (120, 5, 8), (120, 5, 8))

    line = prescribe(a_conditioning_request(BENCH, hit)).lines[0]

    assert (line.change, line.groups[0].load) == ("held", Load(120, "total"))


def test_a_conditioning_line_neither_resets_nor_flags_a_stall() -> None:
    misses = (
        an_exposure("2026-10-12", (120, 5, 8), (120, 5, 8), (120, 5, 8), (120, 4, 9)),
        an_exposure("2026-10-19", (120, 5, 8), (120, 5, 8), (120, 5, 8), (120, 4, 9)),
        an_exposure("2026-10-26", (120, 5, 8), (120, 5, 9), (120, 4, 9), (120, 3, 10)),
    )

    line = prescribe(a_conditioning_request(BENCH, *misses)).lines[0]

    assert (line.change, line.groups[0].load) == ("held", Load(120, "total"))
    assert [flag.code for flag in line.flags] == []
