import datetime

from coach.core.check_in import CheckInDue, LastCheckIn, Window, check_in_due

D = datetime.date
CADENCE = 7


def last_light(date: datetime.date, days: int = 7) -> LastCheckIn:
    return LastCheckIn(date, "light", Window(date - datetime.timedelta(days=days - 1), date))


def test_nothing_is_due_with_no_check_in_and_no_plan() -> None:
    due = check_in_due(D(2026, 11, 1), cadence_days=CADENCE)

    assert due == CheckInDue(due=False, due_on=None, tier="light", window=None)


def test_with_no_row_light_falls_due_a_cadence_after_the_first_plans_monday() -> None:
    monday = D(2026, 11, 2)

    before = check_in_due(D(2026, 11, 7), cadence_days=CADENCE, first_plan_monday=monday)
    on = check_in_due(D(2026, 11, 8), cadence_days=CADENCE, first_plan_monday=monday)

    assert (before.due, before.due_on) == (False, D(2026, 11, 8))
    assert on == CheckInDue(
        due=True, due_on=D(2026, 11, 8), tier="light", window=Window(monday, D(2026, 11, 8))
    )


def test_seven_days_after_the_last_light_row_a_light_check_in_is_due() -> None:
    last = last_light(D(2026, 11, 1))

    six = check_in_due(D(2026, 11, 7), cadence_days=CADENCE, last=last, last_deep=D(2026, 10, 25))
    seven = check_in_due(D(2026, 11, 8), cadence_days=CADENCE, last=last, last_deep=D(2026, 10, 25))

    assert six.due is False
    assert (seven.due, seven.tier, seven.window) == (
        True,
        "light",
        Window(D(2026, 11, 2), D(2026, 11, 8)),
    )


def test_the_cadence_comes_from_the_athlete() -> None:
    due = check_in_due(D(2026, 11, 5), cadence_days=4, last=last_light(D(2026, 11, 1)))

    assert due.due is True


def test_forty_two_days_after_the_last_deep_row_the_tier_is_deep() -> None:
    deep = D(2026, 9, 20)
    last = last_light(D(2026, 10, 25))

    day_41 = check_in_due(D(2026, 10, 31), cadence_days=CADENCE, last=last, last_deep=deep)
    day_42 = check_in_due(D(2026, 11, 1), cadence_days=CADENCE, last=last, last_deep=deep)

    assert day_41.tier == "light"
    assert (day_42.due, day_42.tier) == (True, "deep")


def test_with_no_deep_row_deep_counts_from_the_first_plans_monday() -> None:
    due = check_in_due(
        D(2026, 12, 14),
        cadence_days=CADENCE,
        last=last_light(D(2026, 12, 7)),
        first_plan_monday=D(2026, 11, 2),
    )

    assert due.tier == "deep"


def test_a_defer_deep_review_suppresses_deep_until_its_date() -> None:
    deep = D(2026, 9, 20)
    last = last_light(D(2026, 10, 25))

    on_until = check_in_due(
        D(2026, 11, 1),
        cadence_days=CADENCE,
        last=last,
        last_deep=deep,
        deep_deferred_until=D(2026, 11, 1),
    )
    after = check_in_due(
        D(2026, 11, 2),
        cadence_days=CADENCE,
        last=last,
        last_deep=deep,
        deep_deferred_until=D(2026, 11, 1),
    )

    assert on_until.tier == "light"
    assert after.tier == "deep"


def test_a_window_of_eleven_days_is_a_catch_up_and_stays_light() -> None:
    last = last_light(D(2026, 10, 21))

    due = check_in_due(D(2026, 11, 1), cadence_days=CADENCE, last=last, last_deep=D(2026, 9, 1))

    assert due.window == Window(D(2026, 10, 22), D(2026, 11, 1))
    assert (due.catch_up, due.tier) == (True, "light")


def test_the_check_in_after_a_catch_up_is_deep() -> None:
    catch_up = last_light(D(2026, 11, 1), days=11)

    due = check_in_due(
        D(2026, 11, 8), cadence_days=CADENCE, last=catch_up, last_deep=D(2026, 10, 30)
    )

    assert (due.catch_up, due.tier) == (False, "deep")


def test_a_redesign_adopted_since_the_last_deep_row_makes_the_next_one_deep() -> None:
    due = check_in_due(
        D(2026, 11, 8),
        cadence_days=CADENCE,
        last=last_light(D(2026, 11, 1)),
        last_deep=D(2026, 11, 1),
        redesign_since_deep=True,
    )

    assert due.tier == "deep"


def test_a_light_week_newly_proposed_makes_the_next_one_deep() -> None:
    due = check_in_due(
        D(2026, 11, 8),
        cadence_days=CADENCE,
        last=last_light(D(2026, 11, 1)),
        last_deep=D(2026, 11, 1),
        light_week_proposed=True,
    )

    assert due.tier == "deep"
