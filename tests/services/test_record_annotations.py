import datetime
from typing import Any

import pytest
from support.clock import FixedClock
from support.ledger import a_hevy_workout, a_store, an_exercise

from coach.core.errors import Invalid
from coach.services.query import ledger
from coach.services.record import RecordResult, record
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)
WORKOUT = "b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13"

DISCOUNT = f"""
[[annotation]]
kind = "discount"
target = "workout:{WORKOUT}/bb_bench_press"
params = {{ sets = [2] }}
because = "pain"
text = "shoulder pinched on the last set"
"""


def run(conn: Connection, text: str) -> RecordResult:
    return record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def annotations(conn: Connection, *, open_: bool = False) -> list[dict[str, Any]]:
    return ledger(conn, kind="annotation", id_=None, open_=open_, today=TODAY, last=None).rows


def current(conn: Connection) -> list[str]:
    return [id_ for (id_,) in conn.execute("SELECT id FROM annotation_current ORDER BY id")]


def a_store_with_a_workout() -> Connection:
    conn = a_store()
    an_exercise(conn, "bb_bench_press", hevy_template_id="AAAA0001")
    a_hevy_workout(conn, WORKOUT, templates=(("AAAA0001", "Bench Press (Barbell)"),))
    return conn


def test_an_annotation_on_a_workout_exercise_is_written_with_its_params() -> None:
    conn = a_store_with_a_workout()

    result = run(conn, DISCOUNT)

    assert result.ids == {"annotation": ["a-0001"]}
    [row] = annotations(conn)
    assert (row["id"], row["kind"], row["target"], row["params"], row["because"]) == (
        "a-0001",
        "discount",
        f"workout:{WORKOUT}/bb_bench_press",
        {"sets": [2]},
        "pain",
    )
    assert current(conn) == ["a-0001"]


def test_an_annotation_withdrawn_by_a_later_row_leaves_annotation_current() -> None:
    conn = a_store_with_a_workout()
    run(conn, DISCOUNT)

    result = run(conn, '[[annotation]]\nwithdraws = "a-0001"\n')

    assert result.ids == {"annotation": ["a-0002"]}
    assert result.withdrawn == ["a-0001"]
    assert "a-0001" not in current(conn)
    rows = {r["id"]: r for r in annotations(conn)}
    assert (rows["a-0002"]["withdraws"], rows["a-0002"]["kind"], rows["a-0002"]["target"]) == (
        "a-0001",
        "discount",
        f"workout:{WORKOUT}/bb_bench_press",
    )
    assert rows["a-0001"]["withdrawn_by"] == "a-0002"
    assert annotations(conn, open_=True) == []


@pytest.mark.parametrize(
    ("target", "code"),
    [
        ("a-0009", "draft_ref_unresolved"),
        ("a-0002", "state_conflict"),
        ("a-0001", "state_conflict"),
    ],
)
def test_withdrawing_a_missing_withdrawing_or_withdrawn_annotation_is_refused(
    target: str, code: str
) -> None:
    conn = a_store_with_a_workout()
    run(conn, DISCOUNT)
    run(conn, '[[annotation]]\nwithdraws = "a-0001"\n')

    with pytest.raises(Invalid) as raised:
        run(conn, f'[[annotation]]\nwithdraws = "{target}"\n# again\n')

    assert target in raised.value.message
    assert raised.value.code == code


def test_an_annotation_on_a_workout_that_is_not_stored_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), DISCOUNT)

    assert WORKOUT in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


def test_a_miss_tag_on_a_planned_session_no_plan_covers_is_refused() -> None:
    text = (
        '[[annotation]]\nkind = "miss_tag"\ntarget = "planned_session:2026-11-04/upper-a"\n'
        'because = "schedule"\n'
    )

    with pytest.raises(Invalid) as raised:
        run(a_store(), text)

    assert "planned_session:2026-11-04/upper-a" in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


def test_an_annotation_may_target_a_manual_workout_raised_in_the_same_file() -> None:
    conn = a_store()

    run(
        conn,
        '[[annotation]]\nkind = "void"\ntarget = "workout:@pt"\nbecause = "coach_judgement"\n'
        '[[workout]]\nkey = "pt"\ndate = 2026-10-13\nminutes = 60\n',
    )

    assert annotations(conn)[0]["target"] == "workout:w-0001"


def test_re_running_a_withdrawal_returns_the_same_ids_and_withdrawn_list() -> None:
    conn = a_store_with_a_workout()
    run(conn, DISCOUNT)
    first = run(conn, '[[annotation]]\nwithdraws = "a-0001"\n')

    assert run(conn, '[[annotation]]\nwithdraws = "a-0001"\n') == first


def test_withdrawing_an_annotation_that_is_not_stored_is_an_unresolved_ref() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), '[[annotation]]\nwithdraws = "a-0009"\n')

    assert raised.value.code == "draft_ref_unresolved"
