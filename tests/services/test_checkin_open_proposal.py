import datetime
from typing import cast

from support.check_in_cards import field_of, opened
from support.clock import FixedClock
from support.closed_weeks import a_check_in, a_hard_squat_week, a_planned_squat_week, monday
from support.plans import (
    a_frozen_prescription,
    a_plan_override,
    a_squat_program,
    an_approved_plan,
    squat_logged,
)

from coach.services.record import record
from coach.services.status import StatusResult, status
from coach.store import week_plans
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
    result = status_on(conn, on)
    assert result.block is not None
    return result.block.light_week_pending


def status_on(conn: Connection, on: datetime.date) -> StatusResult:
    clock = FixedClock(datetime.datetime(on.year, on.month, on.day, 12, tzinfo=datetime.UTC))
    return status(
        conn, clock, engine_version="0.4.0", pin="0.4.0", hevy_on=False, exported={}, units="lb"
    )


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


def test_a_light_week_plan_superseded_by_one_without_it_leaves_the_proposal_standing() -> None:
    conn = proposed_and_recorded()
    plan_id = an_approved_plan(conn, monday(5), approved_at="2026-11-30T09:00:00+00:00")
    a_plan_override(conn, plan_id, "light_week", None, None)
    at = "2026-12-01T09:00:00+00:00"
    plan = {
        "id": "wp-2",
        "week": monday(5),
        "position": "A",
        "approved_at": at,
        "write_plan_hash": "sha256:w",
        "draft_hash": "sha256:d2",
        "recorded_at": at,
    }
    with conn:
        week_plans.approve(
            conn, plan, supersedes=plan_id, overrides=[], prescriptions=[], acknowledgements=[]
        )

    block = block_of(conn, datetime.date(2026, 12, 6))

    assert block["standing_from"] == "ci-2026-11-29"
    assert light_week_pending(conn, datetime.date(2026, 12, 2))


def drifting_squat(*, last_reps: int = 8) -> Connection:
    """Two steady squat weeks at RPE 8, then two with two sets at RPE 9."""
    conn = a_squat_program()
    sets = {0: (8, 8, 8, 8), 1: (8, 8, 8, 8), 2: (9, 9, 8, 8), 3: (9, 9, 8, 8)}
    for n, rpes in sets.items():
        a_planned_squat_week(conn, monday(n))
        reps = last_reps if n == 3 else 8
        squat_logged(conn, f"h-{n}", monday(n), *[(120, reps, rpe) for rpe in rpes])
    a_check_in(conn, monday(0), "2026-11-22")
    return conn


def triggers_of(conn: Connection) -> list[object]:
    return cast(list[object], block_of(conn)["triggers"])


def test_rpe_drift_on_two_exposures_after_a_steady_one_is_a_trigger() -> None:
    assert triggers_of(drifting_squat()) == [
        {
            "trigger": "rpe_drift",
            "evidence": ["exposure:h-2/bb_back_squat", "exposure:h-3/bb_back_squat"],
        }
    ]


def test_a_set_longer_than_prescribed_is_not_read_as_drift() -> None:
    assert triggers_of(drifting_squat(last_reps=10)) == []


def test_a_fresh_proposal_keeps_the_standing_one_and_the_deep_tier() -> None:
    conn = four_hard_weeks(readiness="poor")
    aggravated(conn, "2026-11-25")
    a_check_in(conn, "2026-11-23", "2026-11-29", readiness="poor")
    on = datetime.date(2026, 12, 6)

    card = opened(conn, on)
    block = dict(field_of(card, "block").facts)

    assert (card.tier, status_on(conn, on).check_in.tier) == ("deep", "deep")
    assert block["standing_from"] == "ci-2026-11-29"


def test_a_standing_proposal_shows_this_windows_hard_weeks_and_triggers() -> None:
    conn = proposed_and_recorded()
    a_hard_squat_week(conn, monday(4))

    block = block_of(conn, datetime.date(2026, 12, 6))

    assert block["hard_weeks"] == 5
    assert block["triggers"] == [{"trigger": "niggle", "evidence": ["niggle:n-0001"]}]
    assert block["watch"] == "niggle"
    assert (block["proposal"], block["standing_from"]) == ("light_week", "ci-2026-11-29")
    assert block["shape"] == {"set_cut_pct": 40, "load_cut_pct": 10, "rpe_cap": 8}


def test_status_reads_logged_loads_in_the_athletes_units() -> None:
    """Sets heavier than prescribed are not judged for drift, so poor readiness stays a watch."""
    conn = a_squat_program()
    for n, (lb, rpe) in enumerate(((120, 8), (120, 8), (125, 9), (125, 9))):
        plan_id = an_approved_plan(conn, monday(n))
        a_frozen_prescription(
            conn,
            plan_id,
            "lower",
            monday(n),
            "bb_back_squat",
            set_groups=[{"type": "working", "count": 2, "load": 120.0, "range": [6, 8], "rpe": 8}],
            change="held",
        )
        squat_logged(conn, f"h-{n}", monday(n), (lb, 8, rpe), (lb, 8, rpe))
    a_check_in(conn, monday(0), "2026-11-22", readiness="poor")
    a_check_in(conn, "2026-11-23", "2026-11-29")

    assert not light_week_pending(conn, datetime.date(2026, 12, 1))


def test_a_standing_proposal_leaves_the_next_check_ins_light() -> None:
    conn = proposed_and_recorded()
    with conn:
        conn.execute("UPDATE check_in SET tier = 'deep' WHERE id = 'ci-2026-11-29'")

    on = datetime.date(2026, 12, 6)

    card = opened(conn, on)

    assert (card.tier, status_on(conn, on).check_in.tier) == ("light", "light")
    assert dict(field_of(card, "block").facts)["standing_from"] == "ci-2026-11-29"
    assert light_week_pending(conn, on)
