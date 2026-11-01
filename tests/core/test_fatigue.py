import datetime

from coach.core.check_in import Window
from coach.core.closed_week.sessions import TargetSet
from coach.core.cut import LightShape
from coach.core.exposure import ExposureSet
from coach.core.fatigue import (
    DriftExposure,
    NiggleHistory,
    Trigger,
    niggle_trigger,
    propose,
    readiness_trigger,
    rpe_drift,
    short_sleep_week,
)
from coach.core.load import Load
from coach.core.program.form import Deload

CHECK_IN = datetime.date(2026, 11, 8)


def nights(*hours: float) -> dict[datetime.date, float]:
    """Hours for the nights counting back from the night before the check-in."""
    return {CHECK_IN - datetime.timedelta(days=n + 1): h for n, h in enumerate(hours)}


def test_four_short_nights_of_four_measured_is_a_short_sleep_week() -> None:
    trigger = short_sleep_week(nights(6, 6.5, 5, 6.9), CHECK_IN)

    assert trigger is not None
    assert trigger.name == "short_sleep_week"


def test_three_measured_nights_are_too_few_whatever_they_say() -> None:
    assert short_sleep_week(nights(5, 5, 5), CHECK_IN) is None


def test_three_short_nights_of_seven_is_not_a_short_sleep_week() -> None:
    assert short_sleep_week(nights(6, 6, 6, 7, 8, 7.5, 7), CHECK_IN) is None


def test_nights_before_the_seven_do_not_count() -> None:
    old = {CHECK_IN - datetime.timedelta(days=9): 4.0}

    assert short_sleep_week(nights(6, 6, 6, 8) | old, CHECK_IN) is None


WINDOW = Window(datetime.date(2026, 11, 2), CHECK_IN)
POLICY = Deload(
    hard_weeks_ceiling=6, set_cut_pct=40, load_cut_pct=0, rpe_cap=8, test_priority_lifts=False
)


def test_poor_readiness_is_a_trigger_and_ok_is_not() -> None:
    assert readiness_trigger("poor") == Trigger("readiness")
    assert readiness_trigger("ok") is None
    assert readiness_trigger(None) is None


def test_a_niggle_aggravated_inside_the_window_is_a_trigger() -> None:
    niggle = NiggleHistory(
        "n-0001", ((datetime.date(2026, 10, 1), "open"), (CHECK_IN, "aggravated"))
    )

    assert niggle_trigger([niggle], WINDOW) == Trigger("niggle", ("niggle:n-0001",))


def test_a_niggle_still_aggravated_on_the_first_day_is_a_trigger() -> None:
    niggle = NiggleHistory("n-0001", ((datetime.date(2026, 10, 20), "aggravated"),))

    assert niggle_trigger([niggle], WINDOW) == Trigger("niggle", ("niggle:n-0001",))


def test_a_niggle_eased_before_the_window_is_no_trigger() -> None:
    niggle = NiggleHistory(
        "n-0001",
        ((datetime.date(2026, 10, 20), "aggravated"), (datetime.date(2026, 10, 30), "easing")),
    )

    assert niggle_trigger([niggle], WINDOW) is None


def test_two_triggers_propose_a_light_week_with_a_load_cut_when_a_niggle_fired() -> None:
    proposal = propose([Trigger("readiness"), Trigger("niggle")], hard_weeks=3, deload=POLICY)

    assert proposal.state == "propose"
    assert proposal.shape == LightShape(set_cut_pct=40, load_cut_pct=10, rpe_cap=8)


def test_readiness_and_sleep_propose_the_policy_with_the_load_held() -> None:
    triggers = [Trigger("readiness"), Trigger("short_sleep_week")]

    proposal = propose(triggers, hard_weeks=4, deload=POLICY)

    assert proposal.shape == LightShape(set_cut_pct=40, load_cut_pct=0, rpe_cap=8)


def test_one_trigger_is_a_watch() -> None:
    proposal = propose([Trigger("readiness")], hard_weeks=4, deload=POLICY)

    assert (proposal.state, proposal.shape) == ("watch", None)


def test_under_three_hard_weeks_nothing_is_proposed_and_the_card_says_skipped() -> None:
    proposal = propose([Trigger("readiness"), Trigger("niggle")], hard_weeks=2, deload=POLICY)

    assert (proposal.state, proposal.shape) == ("skipped", None)
    assert proposal.line == "skipped (2 hard weeks)"


def test_reaching_the_ceiling_proposes_with_no_trigger_and_cuts_the_load() -> None:
    proposal = propose([], hard_weeks=6, deload=POLICY)

    assert proposal.state == "propose"
    assert proposal.reasons == ("ceiling",)
    assert proposal.shape == LightShape(set_cut_pct=40, load_cut_pct=10, rpe_cap=8)


def test_no_trigger_under_the_ceiling_proposes_nothing() -> None:
    assert propose([], hard_weeks=4, deload=POLICY).line == "none"


def a_set(rpe: float, *, load: float = 100, reps: int = 6) -> ExposureSet:
    return ExposureSet(1, "working", Load(load, "total"), reps, rpe)


TARGET = TargetSet(reps=5, rpe=8, top=6, load=100)


def an_exposure(day: int, *rpes: float, **logged: float) -> DriftExposure:
    on = datetime.date(2026, 10, 19) + datetime.timedelta(days=day)
    load, reps = logged.get("load", 100), int(logged.get("reps", 6))
    sets = tuple((a_set(rpe, load=load, reps=reps), TARGET) for rpe in rpes)
    return DriftExposure("bb_back_squat", on, f"exposure:h-{day}/bb_back_squat", sets)


STEADY = an_exposure(0, 8, 8, 8)


def test_two_drifting_exposures_after_a_steady_one_fire_rpe_drift() -> None:
    drifting = [an_exposure(7, 9, 9, 8), an_exposure(14, 9, 9.5, 8)]

    trigger = rpe_drift([STEADY, *drifting], WINDOW)

    assert trigger == Trigger(
        "rpe_drift", ("exposure:h-7/bb_back_squat", "exposure:h-14/bb_back_squat")
    )


def test_two_drifting_exposures_with_no_steady_one_before_read_as_calibration() -> None:
    assert rpe_drift([an_exposure(7, 9, 9), an_exposure(14, 9, 9)], WINDOW) is None


def test_one_set_over_target_is_no_drift() -> None:
    assert rpe_drift([STEADY, an_exposure(7, 9, 8, 8), an_exposure(14, 9, 9)], WINDOW) is None


def test_a_heavier_set_than_prescribed_is_not_judged() -> None:
    heavier = an_exposure(14, 9, 9, load=105)

    assert rpe_drift([STEADY, an_exposure(7, 9, 9), heavier], WINDOW) is None


def test_a_longer_set_than_prescribed_is_not_judged() -> None:
    longer = an_exposure(14, 9, 9, reps=8)

    assert rpe_drift([STEADY, an_exposure(7, 9, 9), longer], WINDOW) is None


def test_an_extra_set_than_prescribed_is_not_judged() -> None:
    extra = DriftExposure(
        "bb_back_squat",
        datetime.date(2026, 11, 2),
        "exposure:h-14/bb_back_squat",
        ((a_set(9), TARGET), (a_set(9), TARGET)),
        extra=True,
    )

    assert rpe_drift([STEADY, an_exposure(7, 9, 9), extra], WINDOW) is None


def test_the_later_drift_must_fall_inside_the_window() -> None:
    assert rpe_drift([STEADY, an_exposure(1, 9, 9), an_exposure(4, 9, 9)], WINDOW) is None
