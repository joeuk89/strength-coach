import datetime

from support.exposures import an_exposure

from coach.core.closed_week.match import WeekWorkout
from coach.core.closed_week.sessions import (
    AgainstPrescription,
    PlannedWork,
    TargetSet,
    session_outcome,
)
from coach.core.prescription import PlannedSession, StatusSpan

MONDAY = datetime.date(2026, 11, 2)
SQUAT_SETS = (TargetSet(6, 8),) * 6


def lower(
    kind: str = "lifting", tier: str = "core", **targets: tuple[TargetSet, ...]
) -> PlannedWork:
    session = PlannedSession("lower", MONDAY, "home", kind, (), "weekly", tier)
    return PlannedWork(session, targets)


def squat_workout(*sets: tuple[float | None, int, float | None]) -> WeekWorkout:
    exposure = an_exposure("2026-11-02", *sets, workout_id="h-1", exercise_id="bb_back_squat")
    return WeekWorkout("h-1", MONDAY, (exposure,))


def test_two_thirds_of_the_sets_at_a_mean_rpe_one_under_target_pass_the_gate() -> None:
    workout = squat_workout(*[(100, 6, 7.0)] * 4)

    outcome = session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=workout)

    assert (outcome.trained, outcome.in_gate, outcome.passed) == (True, True, True)


def test_a_mean_rpe_one_point_six_under_target_fails_the_gate() -> None:
    workout = squat_workout(*[(100, 6, 6.4)] * 4)

    assert session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=workout).passed is False


def test_under_two_thirds_of_the_sets_logged_fails_the_gate() -> None:
    workout = squat_workout(*[(100, 6, 8.0)] * 3)

    assert session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=workout).passed is False


def test_a_set_with_no_rpe_counts_as_on_target() -> None:
    workout = squat_workout(*[(100, 6, None)] * 3, (100, 6, 6.5))

    assert session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=workout).passed is True


def test_a_coach_led_session_passes_when_it_happened() -> None:
    happened = WeekWorkout("w-1", MONDAY)

    outcome = session_outcome(lower("coach_led"), workout=happened)
    untrained = session_outcome(lower("coach_led"), workout=None)

    assert (outcome.in_gate, outcome.passed) == (True, True)
    assert (untrained.trained, untrained.passed) == (False, False)


def test_a_trained_unlogged_session_is_trained() -> None:
    outcome = session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=None, trained_unlogged=True)

    assert outcome.trained is True


def test_an_untrained_session_on_a_status_span_day_leaves_both_denominators() -> None:
    span = StatusSpan("ill", MONDAY, MONDAY)

    skipped = session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=None, spans=(span,))
    trained = session_outcome(
        lower(bb_back_squat=SQUAT_SETS), workout=squat_workout((100, 6, 8)), spans=(span,)
    )

    assert (skipped.in_gate, skipped.in_adherence) == (False, False)
    assert (trained.in_gate, trained.in_adherence) == (True, True)


def test_a_cancelled_session_leaves_both_denominators() -> None:
    outcome = session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=None, cancelled=True)

    assert (outcome.in_gate, outcome.in_adherence) == (False, False)


def test_a_session_with_no_prescribed_working_set_is_outside_the_gate_only() -> None:
    outcome = session_outcome(lower(), workout=None)

    assert (outcome.in_gate, outcome.in_adherence, outcome.passed) == (False, True, None)


def test_an_optional_session_is_in_neither_denominator() -> None:
    outcome = session_outcome(lower(tier="optional", bb_back_squat=SQUAT_SETS), workout=None)

    assert (outcome.in_gate, outcome.in_adherence) == (False, False)


def test_a_conditioning_session_counts_for_adherence_and_never_the_gate() -> None:
    outcome = session_outcome(lower("conditioning"), workout=None)

    assert (outcome.in_gate, outcome.in_adherence) == (False, True)


def test_the_read_against_the_prescription_is_a_figure_never_the_gate() -> None:
    workout = squat_workout((100, 6, 8.0), (100, 5, 8.0), (100, 6, 6.0), (100, 6, None))

    outcome = session_outcome(lower(bb_back_squat=SQUAT_SETS), workout=workout)

    assert outcome.against == AgainstPrescription(reps_missed=1, effort_off=1, rpe_missing=1)
    assert outcome.passed is True
