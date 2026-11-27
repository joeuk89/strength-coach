from pathlib import Path

from support.fixture_instances import coach, instance, rebuilt

__all__ = ["instance", "rebuilt"]


def test_query_against_reads_the_week_of_the_plan_in_force_by_default(instance: Path) -> None:
    run = coach("query", "against", "--session", "lower-a")

    assert run.code == 0, run.stdout
    rows = run.envelope["result"]["rows"]
    assert [(r["date"], r["session"], r["exercise"]) for r in rows] == [
        ("2026-10-26", "lower-a", "bb_back_squat"),
        ("2026-10-26", "lower-a", "bb_romanian_deadlift"),
    ]


def test_query_against_reads_the_week_holding_the_date_given(instance: Path) -> None:
    planned = coach("query", "against", "--week", "2026-10-28", "--off", "--full")
    unplanned = coach("query", "against", "--week", "2026-10-21")

    rows = planned.envelope["result"]["rows"]
    assert rows
    assert {(r["state"], r["off"]) for r in rows} == {("not_logged", True)}
    assert {r["date"] for r in rows} <= {*(f"2026-10-{day}" for day in range(26, 32)), "2026-11-01"}
    assert unplanned.envelope["result"]["count"] == 0


def test_query_against_refuses_a_week_that_is_not_a_date(instance: Path) -> None:
    run = coach("query", "against", "--week", "last")

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
