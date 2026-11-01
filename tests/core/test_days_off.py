import datetime

from coach.core.days_off import DaysOff, days_off, usual_interval

PLANNED = datetime.date(2026, 11, 2)


def days_before(*counts: int) -> list[datetime.date]:
    return [PLANNED - datetime.timedelta(days=n) for n in counts]


def test_25_days_since_the_lift_with_a_usual_interval_of_7_is_18() -> None:
    lift = days_before(25, 32, 39, 46, 53)

    found = days_off(PLANNED, line_dates=lift, lifting_dates=[*lift, *days_before(3)])

    assert found == DaysOff(days=18, layoff=3, exposure_age=25, usual_interval=7)
    assert found.decayed


def test_a_layoff_longer_than_the_lift_s_overdue_days_wins() -> None:
    lift = days_before(25, 39, 53)

    found = days_off(PLANNED, line_dates=lift, lifting_dates=[*lift, *days_before(20)])

    assert (found.days, found.usual_interval) == (20, 14)


def test_ten_days_off_is_inside_the_grace_and_eleven_is_decayed() -> None:
    assert not days_off(PLANNED, line_dates=[], lifting_dates=days_before(10)).decayed
    assert days_off(PLANNED, line_dates=[], lifting_dates=days_before(11)).decayed


def test_with_no_lifting_at_all_there_are_no_days_off() -> None:
    assert days_off(PLANNED, line_dates=[], lifting_dates=[]).days == 0


def test_the_usual_interval_is_the_median_of_the_last_four_gaps() -> None:
    assert usual_interval(days_before(0, 10, 20, 31, 43, 100)) == 10


def test_the_usual_interval_is_clamped_to_7_to_14() -> None:
    assert usual_interval(days_before(0, 2, 4, 6, 8)) == 7
    assert usual_interval(days_before(0, 20, 40, 60, 80)) == 14


def test_the_usual_interval_reads_the_gaps_there_are() -> None:
    assert usual_interval(days_before(0, 9)) == 9


def test_with_no_gap_the_usual_interval_is_the_floor() -> None:
    assert usual_interval(days_before(0)) == 7
    assert usual_interval([]) == 7


def test_an_even_median_between_whole_days_rounds_down() -> None:
    assert usual_interval(days_before(0, 8, 17)) == 8


def test_two_exposures_on_one_day_are_one_date() -> None:
    assert usual_interval(days_before(0, 0, 9, 9, 18)) == 9
