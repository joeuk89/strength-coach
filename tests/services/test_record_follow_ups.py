import datetime
from typing import Any, cast

import pytest
from support.clock import FixedClock
from support.ledger import a_store, an_exercise

from coach.core.errors import Invalid
from coach.services.query import ledger
from coach.services.record import RecordResult, record
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)

RAISE = """
[[follow_up]]
raised = 2026-10-24
text = "Re-test the deadlift single once the hamstring settles"
due = 2026-11-14
"""


def run(conn: Connection, text: str) -> RecordResult:
    return record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def follow_ups(conn: Connection, *, open_: bool = False) -> list[dict[str, Any]]:
    return ledger(conn, kind="follow_up", id_=None, open_=open_, today=TODAY, last=None).rows


def events(row: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], row["events"])


def an_event(kind: str, date: str, due: str | None = None) -> str:
    due_line = f"due = {due}\n" if due else ""
    return f'[[follow_up]]\nfollow_up = "f-0001"\nkind = "{kind}"\ndate = {date}\n{due_line}'


def test_raising_a_follow_up_writes_a_kept_event_with_the_first_due_date() -> None:
    conn = a_store()

    result = run(conn, RAISE)

    assert result.ids == {"follow_up": ["f-0001"]}
    [row] = follow_ups(conn)
    assert (row["id"], row["raised"], row["kind"], row["due"]) == (
        "f-0001",
        "2026-10-24",
        "kept",
        "2026-11-14",
    )
    assert [(e["id"], e["date"], e["kind"], e["due"]) for e in events(row)] == [
        ("fe-0001", "2026-10-24", "kept", "2026-11-14")
    ]


def test_a_deferred_event_moves_the_due_date_later() -> None:
    conn = a_store()
    run(conn, RAISE)

    run(conn, an_event("deferred", "2026-11-14", "2026-11-28"))

    [row] = follow_ups(conn)
    assert (row["kind"], row["due"]) == ("deferred", "2026-11-28")
    assert len(events(row)) == 2


@pytest.mark.parametrize("due", ["2026-11-14", "2026-11-07"])
def test_a_deferred_event_with_a_due_date_not_later_than_the_previous_is_refused(due: str) -> None:
    conn = a_store()
    run(conn, RAISE)

    with pytest.raises(Invalid) as raised:
        run(conn, an_event("deferred", "2026-11-10", due))

    assert "2026-11-14" in raised.value.message
    assert raised.value.code == "state_conflict"
    assert len(events(follow_ups(conn)[0])) == 1


def test_deferring_after_a_resolved_event_still_compares_with_the_last_due_date() -> None:
    conn = a_store()
    run(conn, RAISE)
    run(conn, an_event("resolved", "2026-11-12"))

    with pytest.raises(Invalid):
        run(conn, an_event("deferred", "2026-11-13", "2026-11-10"))


def test_resolved_and_dropped_follow_ups_leave_the_open_list() -> None:
    conn = a_store()
    run(conn, RAISE + RAISE.replace("Re-test", "Ask about"))

    run(
        conn,
        an_event("resolved", "2026-11-12")
        + an_event("dropped", "2026-11-12").replace("f-0001", "f-0002"),
    )

    assert [r["kind"] for r in follow_ups(conn)] == ["dropped", "resolved"]
    assert follow_ups(conn, open_=True) == []


@pytest.mark.parametrize(
    "text",
    [
        an_event("kept", "2026-11-01"),
        an_event("deferred", "2026-11-01"),
        an_event("resolved", "2026-11-01", "2026-12-01"),
        an_event("snoozed", "2026-11-01", "2026-12-01"),
        RAISE.replace("due = 2026-11-14\n", ""),
        RAISE + 'kind = "kept"\n',
    ],
)
def test_a_follow_up_row_off_its_shape_is_refused(text: str) -> None:
    conn = a_store()
    run(conn, RAISE)

    with pytest.raises(Invalid):
        run(conn, text)


def test_an_event_on_a_follow_up_that_is_not_stored_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), an_event("dropped", "2026-11-01"))

    assert "f-0001" in raised.value.message
    assert raised.value.code == "draft_ref_unresolved"


def test_a_follow_up_about_an_exercise_keeps_the_ref_and_a_note_may_cite_it_by_key() -> None:
    conn = a_store()
    an_exercise(conn, "bb_deadlift")

    run(
        conn,
        RAISE
        + 'about = "exercise:bb_deadlift"\nkey = "retest"\n'
        + '[[note]]\ndate = 2026-10-25\ntext = "keen to test"\nabout = "follow_up:@retest"\n',
    )

    assert follow_ups(conn)[0]["about"] == "exercise:bb_deadlift"
    notes = ledger(conn, kind="note", id_=None, open_=False, today=TODAY, last=None).rows
    assert notes[0]["about"] == "follow_up:f-0001"


def test_re_running_a_follow_up_draft_returns_the_same_ids() -> None:
    conn = a_store()
    first = run(conn, RAISE)

    assert run(conn, RAISE) == first


def test_a_draft_spelling_the_kind_followup_is_refused() -> None:
    conn = a_store()

    with pytest.raises(Invalid) as raised:
        run(conn, RAISE.replace("[[follow_up]]", "[[followup]]"))

    assert "[[followup]] is not a record kind" in raised.value.message
    assert follow_ups(conn) == []


def test_the_ledger_view_refuses_the_kind_followup() -> None:
    with pytest.raises(Invalid):
        ledger(a_store(), kind="followup", id_=None, open_=False, today=TODAY, last=None)
