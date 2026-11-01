import datetime

import pytest
from support.prescribe import PLANNED, a_rotation_form

from coach.core.errors import Invalid
from coach.core.planned_week import choose_sessions, planned_sessions
from coach.core.prescription import PlanOverride


def chosen(
    *overrides: PlanOverride, parked: frozenset[str] = frozenset()
) -> list[tuple[str, str, str]]:
    form = a_rotation_form()
    planned = planned_sessions(form, position="A", monday=PLANNED, parked=parked)
    sessions = choose_sessions(planned, overrides, form=form, monday=PLANNED)
    return [(s.date.isoformat(), s.session_id, s.location) for s in sessions]


def day(n: int) -> datetime.date:
    return PLANNED + datetime.timedelta(days=n)


def test_with_no_override_the_planned_week_stands() -> None:
    assert chosen() == [("2026-11-02", "lower-a", "home"), ("2026-11-05", "push-a", "gym")]


def test_a_minimum_week_keeps_only_its_sessions() -> None:
    assert chosen(PlanOverride("minimum_week", params={"keep": ("push-a",)})) == [
        ("2026-11-05", "push-a", "gym")
    ]


def test_a_one_off_week_with_a_location_relocates_every_session() -> None:
    week = PlanOverride("one_off_week", params={"location": "hotel"})

    assert [location for _, _, location in chosen(week)] == ["hotel", "hotel"]


def test_drop_move_and_relocate_act_on_their_session() -> None:
    assert chosen(PlanOverride("drop_session", "push-a")) == [("2026-11-02", "lower-a", "home")]
    assert chosen(PlanOverride("move_session", "lower-a", params={"to": day(2)}))[0] == (
        "2026-11-04",
        "lower-a",
        "home",
    )
    assert chosen(PlanOverride("relocate_session", "lower-a", params={"location": "gym"}))[0] == (
        "2026-11-02",
        "lower-a",
        "gym",
    )


def test_a_move_outside_the_week_is_a_drop() -> None:
    moved = PlanOverride("move_session", "lower-a", params={"to": day(8)})

    assert [s for _, s, _ in chosen(moved)] == ["push-a"]


def test_an_add_session_on_two_dates_in_one_week_is_admitted() -> None:
    added = chosen(
        PlanOverride("add_session", "pull-b", date=day(2)),
        PlanOverride("add_session", "pull-b", date=day(5), params={"location": "gym"}),
    )

    assert ("2026-11-04", "pull-b", "home") in added
    assert ("2026-11-07", "pull-b", "gym") in added


def test_a_parked_session_is_absent_and_an_add_session_resumes_it_for_one_week() -> None:
    assert chosen(parked=frozenset({"push-a"})) == [("2026-11-02", "lower-a", "home")]
    assert ("2026-11-06", "push-a", "gym") in chosen(
        PlanOverride("add_session", "push-a", date=day(4)), parked=frozenset({"push-a"})
    )


def test_an_add_session_names_a_session_the_version_or_a_niggle_carries() -> None:
    with pytest.raises(Invalid) as raised:
        chosen(PlanOverride("add_session", "yoga", date=day(1)))

    assert "yoga" in raised.value.message


@pytest.mark.parametrize("offset", [-1, 7, 18])
def test_an_add_session_dated_outside_the_week_is_refused(offset: int) -> None:
    with pytest.raises(Invalid) as raised:
        chosen(PlanOverride("add_session", "pull-b", date=day(offset)))

    assert raised.value.code == "invalid_argument"
    assert day(offset).isoformat() in raised.value.message


def test_an_override_on_a_session_not_planned_this_week_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        chosen(PlanOverride("hold", "pull-b", "bb_back_squat"))

    assert "pull-b" in raised.value.message


def test_a_line_override_on_an_added_session_is_admitted() -> None:
    added = PlanOverride("add_session", "pull-b", date=day(2))
    hold = PlanOverride("hold", "pull-b", "bb_back_squat")

    assert ("2026-11-04", "pull-b", "home") in chosen(added, hold)


def test_a_line_override_on_an_added_session_names_one_of_its_lines() -> None:
    added = PlanOverride("add_session", "pull-b", date=day(2))

    with pytest.raises(Invalid) as raised:
        chosen(added, PlanOverride("hold", "pull-b", "bb_bench_press"))

    assert "bb_bench_press" in raised.value.message


def test_a_session_override_on_a_session_only_added_this_week_is_refused() -> None:
    added = PlanOverride("add_session", "pull-b", date=day(2))

    with pytest.raises(Invalid) as raised:
        chosen(added, PlanOverride("drop_session", "pull-b"))

    assert "pull-b" in raised.value.message
