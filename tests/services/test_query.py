import datetime

import pytest
from support.clock import FixedClock
from support.ledger import a_store, a_weigh_in, an_exercise

from coach.core.errors import Invalid
from coach.services.query import ledger, readings
from coach.services.record import record
from coach.store.connection import Connection

TODAY = datetime.date(2026, 10, 30)


def recorded(conn: Connection, text: str) -> None:
    record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def test_readings_of_one_kind_keep_the_newest_and_say_more_exist() -> None:
    conn = a_store()
    for day in range(1, 6):
        a_weigh_in(conn, f"2026-10-0{day}", 80.0 + day, id_=f"wi-000{day}")

    result = readings(conn, kind="weigh_in", last=3)

    assert [row["id"] for row in result.rows] == ["wi-0005", "wi-0004", "wi-0003"]
    assert result.count == 5
    assert result.truncated is True
    assert result.rows[0] == {
        "record_kind": "weigh_in",
        "id": "wi-0005",
        "date": "2026-10-05",
        "kg": 85.0,
        "source": "manual",
    }


def test_readings_skip_withdrawn_and_withdrawing_rows() -> None:
    conn = a_store()
    a_weigh_in(conn, "2026-10-01", 28.0, id_="wi-0001")
    recorded(
        conn, '[[weigh_in]]\nwithdraws = "wi-0001"\n[[weigh_in]]\ndate = 2026-10-01\nkg = 82\n'
    )

    result = readings(conn, kind="weigh_in", last=10)

    assert [row["id"] for row in result.rows] == ["wi-0003"]
    assert result.truncated is False


def test_readings_without_a_kind_merge_every_kind_newest_first() -> None:
    conn = a_store()
    recorded(
        conn,
        "[[sleep_night]]\nnight = 2026-10-28\nhours = 7.5\n"
        "[[weigh_in]]\ndate = 2026-10-29\nkg = 82\n"
        '[[activity]]\ndate = 2026-10-27\nkind = "run"\nminutes = 30\nrpe = 6\nquality = true\n',
    )

    result = readings(conn, kind=None, last=10)

    assert [row["id"] for row in result.rows] == ["wi-0001", "sn-0001", "ac-0001"]
    assert result.rows[1] == {
        "record_kind": "sleep_night",
        "id": "sn-0001",
        "night": "2026-10-28",
        "hours": 7.5,
        "source": "manual",
    }
    assert result.rows[2]["quality"] is True
    assert result.rows[2]["source"] == "manual"


def test_readings_refuse_a_kind_that_is_not_a_reading() -> None:
    with pytest.raises(Invalid):
        readings(a_store(), kind="note", last=10)


def test_ledger_by_kind_lists_withdrawals_on_both_rows() -> None:
    conn = a_store()
    recorded(conn, '[[status_span]]\nkind = "ill"\nfrom_date = 2026-10-20\nto_date = 2026-10-22\n')
    recorded(conn, '[[status_span]]\nwithdraws = "ss-0001"\n')

    result = ledger(conn, kind="status_span", id_=None, open_=False, today=TODAY, last=10)

    assert [(r["id"], r["withdraws"], r["withdrawn_by"]) for r in result.rows] == [
        ("ss-0002", "ss-0001", None),
        ("ss-0001", None, "ss-0002"),
    ]


def test_ledger_open_keeps_live_status_spans_that_have_not_ended() -> None:
    conn = a_store()
    recorded(
        conn,
        '[[status_span]]\nkind = "ill"\nfrom_date = 2026-10-01\nto_date = 2026-10-03\n'
        '[[status_span]]\nkind = "travel"\nfrom_date = 2026-10-29\n'
        '[[status_span]]\nkind = "injured"\nfrom_date = 2026-10-25\nto_date = 2026-11-02\n',
    )

    result = ledger(conn, kind="status_span", id_=None, open_=True, today=TODAY, last=10)

    assert [r["id"] for r in result.rows] == ["ss-0002", "ss-0003"]


def test_ledger_by_id_finds_the_kind_from_the_prefix() -> None:
    conn = a_store()
    recorded(conn, '[[note]]\ndate = 2026-10-29\ntext = "knee clicks"\n')

    result = ledger(conn, kind=None, id_="an-0001", open_=False, today=TODAY, last=10)

    assert result.rows == [
        {
            "record_kind": "note",
            "id": "an-0001",
            "date": "2026-10-29",
            "text": "knee clicks",
            "about": None,
            "check_in": None,
            "draft_hash": result.rows[0]["draft_hash"],
            "recorded_at": "2026-10-30T12:00:00+00:00",
        }
    ]


def test_ledger_by_id_falls_back_to_the_library() -> None:
    conn = a_store()
    an_exercise(conn, "bb_bench_press", hevy_template_id="AAAA0001")

    result = ledger(conn, kind=None, id_="bb_bench_press", open_=False, today=TODAY, last=10)

    assert result.rows[0]["record_kind"] == "exercise"
    assert result.rows[0]["hevy_template_id"] == "AAAA0001"
    assert result.rows[0]["muscles"] == {"primary": ["chest"], "secondary": []}


def test_ledger_lists_a_manual_workout_with_its_sets() -> None:
    conn = a_store()
    recorded(conn, '[[workout]]\ndate = 2026-10-13\ntitle = "PT session"\nminutes = 60\n')

    result = ledger(conn, kind="workout", id_=None, open_=True, today=TODAY, last=10)

    row = result.rows[0]
    assert (row["id"], row["source"], row["minutes"], row["sets"]) == ("w-0001", "manual", 60, [])


def test_ledger_needs_a_kind_or_an_id() -> None:
    with pytest.raises(Invalid):
        ledger(a_store(), kind=None, id_=None, open_=False, today=TODAY, last=10)


def test_ledger_names_an_unknown_record_kind() -> None:
    with pytest.raises(Invalid) as raised:
        ledger(a_store(), kind="nigle", id_=None, open_=False, today=TODAY, last=10)

    assert "nigle" in raised.value.message
