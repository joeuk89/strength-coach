import datetime

from support.check_in_cards import field_of, opened
from support.clock import FixedClock
from support.closed_weeks import a_check_in, a_hard_squat_week, monday
from support.plans import a_plan_override, a_squat_program, an_approved_plan

from coach.services.record import record
from coach.services.status import status
from coach.store.connection import Connection

FOURTH_SUNDAY = datetime.date(2026, 11, 29)


def aggravated(conn: Connection, on: str) -> None:
    niggle = (
        f'[[niggle]]\nsite = "left knee"\nopened = 2026-10-20\ndate = {on}\n'
        'status = "aggravated"\n'
        'constraints = [{ kind = "rpe_cap", pattern = "squat", value = 7 }]\n'
    )
    record(conn, niggle.encode(), file="n.toml", clock=FixedClock())


def four_hard_weeks(*, readiness: str) -> Connection:
    """Four hard squat weeks; the first three closed by a check-in reporting `readiness`."""
    conn = a_squat_program()
    for n in range(4):
        a_hard_squat_week(conn, monday(n))
    a_check_in(conn, monday(0), "2026-11-22", readiness=readiness)
    return conn


def block_of(conn: Connection, on: datetime.date = FOURTH_SUNDAY) -> dict[str, object]:
    return dict(field_of(opened(conn, on), "block").facts)


def light_week_pending(conn: Connection, on: datetime.date) -> bool:
    clock = FixedClock(datetime.datetime(on.year, on.month, on.day, 12, tzinfo=datetime.UTC))
    result = status(conn, clock, engine_version="0.4.0", pin="0.4.0", hevy_on=False, exported={})
    assert result.block is not None
    return result.block.light_week_pending


def test_poor_readiness_and_an_aggravated_niggle_propose_a_light_week_with_a_load_cut() -> None:
    conn = four_hard_weeks(readiness="poor")
    aggravated(conn, "2026-11-25")

    block = block_of(conn)

    assert block["hard_weeks"] == 4
    assert block["proposal"] == "light_week"
    assert block["triggers"] == [
        {"trigger": "readiness", "evidence": []},
        {"trigger": "niggle", "evidence": ["niggle:n-0001"]},
    ]
    assert block["shape"] == {"set_cut_pct": 40, "load_cut_pct": 10, "rpe_cap": 8}


def test_poor_readiness_alone_is_a_watch() -> None:
    conn = four_hard_weeks(readiness="poor")

    block = block_of(conn)

    assert (block["proposal"], block["watch"]) == ("none", "readiness")


def test_under_three_hard_weeks_the_block_line_says_skipped() -> None:
    conn = a_squat_program()
    for n in range(2):
        a_hard_squat_week(conn, monday(n))
    a_check_in(conn, monday(0), "2026-11-08", readiness="poor")
    aggravated(conn, "2026-11-10")

    assert block_of(conn, datetime.date(2026, 11, 15))["proposal"] == "skipped (2 hard weeks)"


def proposed_and_recorded() -> Connection:
    """The proposal above, then the check-in that opened it recorded with readiness `ok`."""
    conn = four_hard_weeks(readiness="poor")
    aggravated(conn, "2026-11-25")
    a_check_in(conn, "2026-11-23", "2026-11-29", readiness="ok")
    return conn


def test_the_proposal_stands_at_the_next_checkin_open() -> None:
    conn = proposed_and_recorded()

    block = block_of(conn, datetime.date(2026, 12, 6))

    assert (block["proposal"], block["standing_from"]) == ("light_week", "ci-2026-11-29")
    assert light_week_pending(conn, datetime.date(2026, 12, 1))


def test_a_plan_carrying_light_week_clears_the_proposal() -> None:
    conn = proposed_and_recorded()
    plan_id = an_approved_plan(conn, monday(5), approved_at="2026-11-30T09:00:00+00:00")
    a_plan_override(conn, plan_id, "light_week", None, None)

    block = block_of(conn, datetime.date(2026, 12, 6))

    assert "standing_from" not in block
    assert not light_week_pending(conn, datetime.date(2026, 12, 1))
