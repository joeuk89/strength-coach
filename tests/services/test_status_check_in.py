import datetime

import pytest
from support.clock import FixedClock
from support.goals import WORKED

from coach.core.check_in import CheckInDue, Window
from coach.core.errors import Invalid
from coach.services.checkin_record import checkin_record
from coach.services.goal_adopt import goal_adopt
from coach.services.query import ledger
from coach.services.record import record
from coach.services.status import StatusResult, status
from coach.store.catalogue import seed_catalogue
from coach.store.connection import Connection, open_store

D = datetime.date
ENGINE = "0.4.0"


def at(day: datetime.date) -> FixedClock:
    return FixedClock(datetime.datetime(day.year, day.month, day.day, 18, tzinfo=datetime.UTC))


def status_on(conn: Connection, day: datetime.date) -> StatusResult:
    return status(
        conn, at(day), engine_version=ENGINE, pin=ENGINE, hevy_on=False, exported={}, units="lb"
    )


def a_check_in(conn: Connection, day: str, tier: str = "light", extra: str = "") -> None:
    text = f'date = {day}\ntier = "{tier}"\nread = "read of {day}"\n{extra}'
    checkin_record(conn, text.encode("utf-8"), file="ci.toml", clock=at(D.fromisoformat(day)))


def test_seven_days_after_the_last_light_row_status_says_a_light_check_in_is_due() -> None:
    conn = open_store(":memory:")
    a_check_in(conn, "2026-11-01", extra="window_start = 2026-10-26\n")

    six = status_on(conn, D(2026, 11, 7)).check_in
    seven = status_on(conn, D(2026, 11, 8)).check_in

    assert (six.due, six.due_on) == (False, D(2026, 11, 8))
    assert seven == CheckInDue(
        due=True, due_on=D(2026, 11, 8), tier="light", window=Window(D(2026, 11, 2), D(2026, 11, 8))
    )


def weekly(conn: Connection, deep: str, last: str) -> None:
    """A deep check-in, then a light one every seven days up to `last`."""
    day = D.fromisoformat(deep)
    a_check_in(conn, deep, "deep")
    while day < D.fromisoformat(last):
        day += datetime.timedelta(days=7)
        a_check_in(conn, day.isoformat())


def test_forty_two_days_after_the_last_deep_row_status_says_deep() -> None:
    conn = open_store(":memory:")
    weekly(conn, "2026-09-20", "2026-10-25")

    assert status_on(conn, D(2026, 10, 31)).check_in.tier == "light"
    assert status_on(conn, D(2026, 11, 1)).check_in.tier == "deep"


def test_a_defer_deep_review_decision_suppresses_deep_until_its_date() -> None:
    conn = open_store(":memory:")
    weekly(conn, "2026-09-20", "2026-10-18")
    a_check_in(
        conn,
        "2026-10-25",
        extra='[[decision]]\nkind = "defer_deep_review"\nuntil = 2026-11-02\n'
        'because = "schedule"\ntext = "travelling; the deep pass waits"\n',
    )

    assert status_on(conn, D(2026, 11, 2)).check_in.tier == "light"
    assert status_on(conn, D(2026, 11, 3)).check_in.tier == "deep"


def test_a_window_of_eleven_days_is_a_catch_up_and_defers_deep_to_the_next_check_in() -> None:
    conn = open_store(":memory:")
    weekly(conn, "2026-10-04", "2026-10-18")

    catch_up = status_on(conn, D(2026, 10, 29)).check_in
    a_check_in(conn, "2026-10-29")
    after = status_on(conn, D(2026, 11, 5)).check_in

    assert catch_up.window == Window(D(2026, 10, 19), D(2026, 10, 29))
    assert (catch_up.catch_up, catch_up.tier) == (True, "light")
    assert (after.catch_up, after.tier) == (False, "deep")


def test_status_counts_open_niggles_due_follow_ups_decisions_and_observations() -> None:
    conn = open_store(":memory:")
    a_check_in(
        conn,
        "2026-11-01",
        extra='[[niggle]]\nsite = "knee"\ndate = 2026-11-01\nstatus = "reported"\n'
        '[[niggle]]\nsite = "wrist"\ndate = 2026-11-01\nstatus = "resolved"\n'
        '[[follow_up]]\ntext = "retest"\nraised = 2026-11-01\ndue = 2026-11-03\n'
        '[[follow_up]]\ntext = "later"\nraised = 2026-11-01\ndue = 2026-12-01\n'
        '[[decision]]\nkind = "defer_deep_review"\nuntil = 2026-11-02\n'
        'because = "schedule"\ntext = "x"\n'
        '[[decision]]\nkind = "training_max"\nexercise = "bb_bench_press"\nload = 100\n'
        'because = "coach_judgement"\ntext = "x"\n'
        '[[exercise]]\nid = "bb_bench_press"\nname = "Bench"\npattern = "push"\n'
        'muscles = { primary = ["chest"], secondary = [] }\nload_mode = "total"\n'
        'equipment_kind = "barbell"\nhevy_template_id = "T1"\nhevy_title = "Bench"\n'
        '[[observation]]\ntext = "drift adds volume"\n'
        '[[observation]]\ntext = "drift adds intensity"\n',
    )
    a_check_in(conn, "2026-11-02", extra='[[observation]]\nretire = "o-0001"\nbecause = "gone"\n')

    result = status_on(conn, D(2026, 11, 3))

    assert result.niggles == ("n-0001",)
    assert result.follow_ups_due == ("f-0001",)
    assert result.decisions == {"training_max": ("d-0002",)}
    assert result.observations == ("o-0002",)
    assert [w.key for w in result.warnings] == [
        "followup_due@instance",
        "niggle_unconstrained@instance",
        "training_max_unused@exercise:bb_bench_press",
    ]


CUTOVER = """date = 2026-11-01
tier = "deep"
read = "state carried from the old instance"
window_start = 2026-10-26

[[niggle]]
key = "hamstring"
site = "hamstring after runs"
opened = 2026-08-14
date = 2026-11-01
status = "easing"
text = "flares after longer runs; easing since the cap"
constraints = [{ kind = "rpe_cap", pattern = "hinge", value = 7 }]

[[niggle]]
key = "shoulder"
site = "left shoulder"
opened = 2026-09-02
date = 2026-11-01
status = "easing"
constraints = [{ kind = "rpe_cap", exercise = "db_lateral_raise", value = 7 }]

[[observation]]
text = "drift adds volume"
[[observation]]
text = "drift adds intensity on top sets"
[[observation]]
text = "coach-led sessions run hard whatever is asked"
[[observation]]
text = "coach-led sessions go under-logged"
[[observation]]
text = "the coach's A/B alternation is unreliable"
[[observation]]
text = "active holidays are training stress"
[[observation]]
text = "the coach rarely programmes deadlifts"

[[decision]]
kind = "activity_cap"
activity_kind = "run"
weekly_distance = 17
single_distance = 6
because = "pain"
text = "runs capped while the hamstring settles"
evidence = ["niggle:@hamstring"]

[[workout]]
date = 2026-10-06
title = "Coach-led session"
minutes = 60

[[workout]]
date = 2026-10-13
title = "Coach-led session"
minutes = 60
session_rpe = 9
"""


def test_the_synthetic_cutover_draft_yields_the_acceptance_status() -> None:
    conn = open_store(":memory:")
    with conn:
        seed_catalogue(conn)
    goal_adopt(conn, WORKED.encode("utf-8"), file="g.toml", clock=at(D(2026, 11, 1)))

    written = checkin_record(
        conn, CUTOVER.encode("utf-8"), file="ci.toml", clock=at(D(2026, 11, 1))
    )
    result = status_on(conn, D(2026, 11, 1))

    hamstring = written.ids["niggle"][0]
    assert result.niggles == ("n-0001", "n-0002")
    assert "niggle_unconstrained" not in {w.code for w in result.warnings}
    assert len(result.observations) == 7
    assert result.decisions == {"activity_cap": ("d-0001",)}
    [cap] = ledger(
        conn, kind="decision", id_="d-0001", open_=False, today=D(2026, 11, 1), last=None
    ).rows
    assert cap["evidence"] == [f"niggle:{hamstring}"]
    assert result.workouts == {"hevy": 0, "manual": 2}
    assert result.goal is not None and result.phase is not None


def test_a_record_file_cannot_carry_an_observation_after_a_check_in_exists() -> None:
    conn = open_store(":memory:")
    a_check_in(conn, "2026-11-01")

    with pytest.raises(Invalid) as raised:
        record(conn, b'[[observation]]\ntext = "x"\n', file="r.toml", clock=at(D(2026, 11, 2)))

    assert raised.value.code == "record_kind_not_allowed"
