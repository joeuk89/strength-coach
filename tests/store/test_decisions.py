import datetime

from support.ledger import a_store

from coach.core.prescription import DecisionInForce
from coach.store import decisions
from coach.store.connection import Connection

PARIS_SUMMER = datetime.timezone(datetime.timedelta(hours=2))


def a_decision(
    conn: Connection,
    id_: str,
    kind: str,
    *,
    recorded_at: str = "2026-11-02T12:00:00+00:00",
    until: str | None = "2026-11-30",
) -> None:
    with conn:
        decisions.insert_decision(
            conn,
            {
                "id": id_,
                "kind": kind,
                "session_id": None,
                "exercise_id": None,
                "params": {"rung": 2},
                "until": until,
                "because": "progress",
                "text": "why",
                "evidence": None,
                "superseded_by": None,
                "retired_by": None,
                "check_in": None,
                "draft_hash": "sha256:d",
                "recorded_at": recorded_at,
            },
        )


def test_a_decision_is_dated_by_the_day_it_was_recorded_on_in_the_athletes_zone() -> None:
    conn = a_store()
    a_decision(conn, "d-1", "training_max", recorded_at="2026-11-02T23:30:00+00:00")

    [found] = decisions.in_force_dated(conn, None, ("training_max",), PARIS_SUMMER)

    assert found == DecisionInForce(
        id="d-1",
        kind="training_max",
        params={"rung": 2},
        on=datetime.date(2026, 11, 3),
    )


def test_only_the_kinds_asked_for_are_read() -> None:
    conn = a_store()
    a_decision(conn, "d-1", "training_max")
    a_decision(conn, "d-2", "safety_ceiling")
    a_decision(conn, "d-3", "ladder_rung")

    found = decisions.in_force_dated(conn, None, ("training_max", "ladder_rung"), datetime.UTC)

    assert [d.id for d in found] == ["d-1", "d-3"]


def test_a_date_leaves_out_a_decision_whose_until_has_passed() -> None:
    conn = a_store()
    a_decision(conn, "d-1", "training_max", until="2026-11-08")
    a_decision(conn, "d-2", "training_max", until="2026-11-09")

    found = decisions.in_force_dated(
        conn, datetime.date(2026, 11, 9), ("training_max",), datetime.UTC
    )

    assert [d.id for d in found] == ["d-2"]
