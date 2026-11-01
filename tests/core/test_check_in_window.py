import datetime

import pytest

from coach.core.check_in import Window, check_in_window
from coach.core.errors import Invalid

D = datetime.date


def test_the_first_row_takes_the_files_window_start() -> None:
    window = check_in_window(D(2026, 11, 1), file_start=D(2026, 10, 26))

    assert window == Window(D(2026, 10, 26), D(2026, 11, 1))


def test_the_first_row_with_no_window_start_starts_on_the_first_plans_monday() -> None:
    window = check_in_window(D(2026, 11, 8), first_plan_monday=D(2026, 11, 2))

    assert window == Window(D(2026, 11, 2), D(2026, 11, 8))


def test_the_first_row_with_no_plan_and_no_window_start_is_its_own_date() -> None:
    assert check_in_window(D(2026, 11, 1)) == Window(D(2026, 11, 1), D(2026, 11, 1))


def test_a_later_row_starts_the_day_after_the_previous_window_end() -> None:
    window = check_in_window(
        D(2026, 11, 8), previous_end=D(2026, 11, 1), first_plan_monday=D(2026, 10, 26)
    )

    assert window == Window(D(2026, 11, 2), D(2026, 11, 8))


def test_a_later_row_setting_window_start_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        check_in_window(D(2026, 11, 8), previous_end=D(2026, 11, 1), file_start=D(2026, 11, 2))

    assert raised.value.code == "state_conflict"


def test_a_date_inside_the_previous_window_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        check_in_window(D(2026, 11, 1), previous_end=D(2026, 11, 1))

    assert raised.value.code == "state_conflict"


def test_a_window_start_after_the_date_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        check_in_window(D(2026, 11, 1), file_start=D(2026, 11, 2))

    assert raised.value.code == "state_conflict"


@pytest.mark.parametrize(("days", "catch_up"), [(10, False), (11, True)])
def test_a_window_longer_than_ten_days_is_a_catch_up(days: int, catch_up: bool) -> None:
    start = D(2026, 11, 1)

    window = Window(start, start + datetime.timedelta(days=days - 1))

    assert window.catch_up is catch_up


def test_a_first_plan_starting_after_the_date_leaves_the_window_on_the_date() -> None:
    window = check_in_window(D(2026, 11, 1), first_plan_monday=D(2026, 11, 2))

    assert window == Window(D(2026, 11, 1), D(2026, 11, 1))
