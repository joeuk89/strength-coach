import datetime

from support.prescribe import a_conditioning_request, a_line, a_request, working

from coach.core.prescribe import prescribe
from coach.core.prescription import ConditioningDose, MatchedActivity
from coach.core.program.form import SchemeRef

EMOM = SchemeRef(
    "emom_density",
    {
        "minutes": 12,
        "minutes_cap": 16,
        "minutes_step": 2,
        "reps": {"kb_swing": 12},
        "reps_cap": {"kb_swing": 14},
        "rpe_target": 7,
    },
)
CIRCUIT = SchemeRef(
    "circuit_rounds",
    {
        "rounds": 3,
        "rounds_cap": 4,
        "time_cap_minutes": 20,
        "reps": {"kb_swing": 10},
        "rpe_target": 7,
    },
)
SWING = a_line("kb_swing", working(1, 12, None), scheme="hold", start_load=24)
LAST_WEEK = datetime.date(2026, 10, 27)


def swings(
    minutes: int, reps: int, rpe: float | None = 7, rounds: int | None = None
) -> MatchedActivity:
    return MatchedActivity(LAST_WEEK, minutes, rpe, {"kb_swing": reps}, rounds)


def dose(scheme: SchemeRef, activity: MatchedActivity | None) -> ConditioningDose | None:
    return prescribe(a_conditioning_request(scheme, SWING, activity=activity)).dose


def test_an_emom_at_or_under_rpe_target_steps_the_minutes() -> None:
    found = dose(EMOM, swings(12, 12))

    assert found is not None
    assert (found.minutes, dict(found.reps), found.change) == (14, {"kb_swing": 12}, "12 → 14 min")
    assert found.derived_from == "activity:2026-10-27"


def test_an_emom_steps_the_minutes_no_further_than_the_cap() -> None:
    found = dose(EMOM, swings(15, 12))

    assert found is not None and found.minutes == 16


def test_an_emom_at_the_minutes_cap_steps_the_reps_to_their_cap() -> None:
    stepped = dose(EMOM, swings(16, 13))
    capped = dose(EMOM, swings(16, 14))

    assert stepped is not None and (stepped.minutes, dict(stepped.reps)) == (16, {"kb_swing": 14})
    assert capped is not None and (dict(capped.reps), capped.change) == ({"kb_swing": 14}, "held")


def test_an_emom_over_rpe_target_holds() -> None:
    found = dose(EMOM, swings(12, 12, rpe=8))

    assert found is not None and (found.minutes, found.change) == (12, "held")


def test_with_no_matched_activity_the_params_stand_as_authored() -> None:
    found = dose(EMOM, None)

    assert found == ConditioningDose(
        "emom_density", 12, None, {"kb_swing": 12}, "params", "as authored"
    )


def test_a_circuit_steps_one_round_then_the_reps() -> None:
    rounds = dose(CIRCUIT, swings(20, 10, rounds=3))
    reps = dose(CIRCUIT, swings(20, 10, rounds=4))

    assert rounds is not None and (rounds.rounds, dict(rounds.reps)) == (4, {"kb_swing": 10})
    assert reps is not None and (reps.rounds, dict(reps.reps)) == (4, {"kb_swing": 11})


def test_a_conditioning_sessions_lines_run_hold() -> None:
    progressing = a_line("kb_swing", working(1, 12, None), start_load=24)

    session = prescribe(a_conditioning_request(EMOM, progressing))

    assert [line.scheme for line in session.lines] == ["hold"]


def test_a_lifting_session_has_no_dose() -> None:
    assert prescribe(a_request()).dose is None
