import datetime

from coach.core.goal import Until
from coach.core.phase_trend import (
    PhaseInForce,
    fourteen_day_average,
    observed_rate,
    phase_condition_met,
    phase_trend_off,
)

TODAY = datetime.date(2026, 11, 29)
COACHS_CALL = Until("coachs_call")


def daily(
    start: datetime.date, days: int, kg: float, step: float = 0
) -> dict[datetime.date, float]:
    return {start + datetime.timedelta(days=n): kg + step * n for n in range(days)}


def a_phase(kind: str = "deficit", rate: float = -0.5, until: Until = COACHS_CALL) -> PhaseInForce:
    return PhaseInForce("ph-0001", kind, rate, until, opened=datetime.date(2026, 10, 1))


def test_the_14_day_average_reads_the_14_days_ending_on_the_date() -> None:
    weigh_ins = {
        TODAY: 80.0,
        TODAY - datetime.timedelta(days=13): 82.0,
        TODAY - datetime.timedelta(days=14): 99.0,
    }

    assert fourteen_day_average(weigh_ins, TODAY) == 81.0


def test_with_no_weigh_in_in_the_14_days_there_is_no_average() -> None:
    assert fourteen_day_average({TODAY - datetime.timedelta(days=20): 80.0}, TODAY) is None


def test_the_observed_rate_is_the_weekly_change_against_the_average_28_days_earlier() -> None:
    weigh_ins = {TODAY: 79.2, TODAY - datetime.timedelta(days=28): 80.0}

    assert observed_rate(weigh_ins, TODAY) == -0.25


def test_a_rate_outside_the_band_after_28_days_of_weigh_ins_raises_phase_trend_off() -> None:
    weigh_ins = {TODAY: 80.0, TODAY - datetime.timedelta(days=28): 80.0}

    flag = phase_trend_off(a_phase(), weigh_ins, TODAY)

    assert flag is not None
    assert flag.params == {
        "phase_id": "ph-0001",
        "target_rate": -0.5,
        "observed_rate": 0.0,
        "window": ["2026-11-01", "2026-11-29"],
    }


def test_a_rate_inside_the_band_raises_nothing() -> None:
    weigh_ins = {TODAY: 78.8, TODAY - datetime.timedelta(days=28): 80.0}

    assert phase_trend_off(a_phase(), weigh_ins, TODAY) is None


def test_under_28_days_of_weigh_ins_the_trend_is_not_judged() -> None:
    weigh_ins = {TODAY: 80.0, TODAY - datetime.timedelta(days=20): 80.0}

    assert phase_trend_off(a_phase(), weigh_ins, TODAY) is None


def test_maintenance_reads_a_fixed_band_around_zero() -> None:
    steady = {TODAY: 80.4, TODAY - datetime.timedelta(days=28): 80.0}
    rising = {TODAY: 81.2, TODAY - datetime.timedelta(days=28): 80.0}
    phase = a_phase("maintenance", 0)

    assert phase_trend_off(phase, steady, TODAY) is None
    assert phase_trend_off(phase, rising, TODAY) is not None


def test_a_14_day_average_at_the_bodyweight_condition_raises_phase_condition_met() -> None:
    phase = a_phase(until=Until("bodyweight_at_or_below", 176))
    weigh_ins = daily(TODAY - datetime.timedelta(days=13), 14, 79.8)

    flag = phase_condition_met(phase, weigh_ins, TODAY, units="lb")

    assert flag is not None
    assert flag.params == {
        "phase_id": "ph-0001",
        "condition": "bodyweight_at_or_below",
        "value": 175.9,
    }


def test_an_average_above_an_at_or_below_condition_raises_nothing() -> None:
    phase = a_phase(until=Until("bodyweight_at_or_below", 78))

    assert phase_condition_met(phase, {TODAY: 80.0}, TODAY, units="kg") is None


def test_a_date_condition_is_met_on_its_date() -> None:
    phase = a_phase(until=Until("date", TODAY))

    flag = phase_condition_met(phase, {}, TODAY, units="kg")

    assert flag is not None
    assert flag.params["value"] == "2026-11-29"


def test_the_coachs_call_is_never_met_by_code() -> None:
    assert phase_condition_met(a_phase(), {TODAY: 70.0}, TODAY, units="kg") is None
