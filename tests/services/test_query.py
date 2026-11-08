import datetime
from typing import Any

import pytest
from support.clock import FixedClock
from support.ledger import a_store, a_weigh_in, an_exercise

from coach.core.errors import Invalid
from coach.services.checkin_record import checkin_record
from coach.services.query import exercises, ledger, readings
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


def checked_in(conn: Connection, date: str, body: str) -> None:
    text = f'date = {date}\ntier = "light"\nread = "a steady week"\n{body}'
    checkin_record(conn, text.encode("utf-8"), file="ci.toml", clock=FixedClock())


def observations_raised_and_one_retired() -> Connection:
    conn = a_store()
    checked_in(
        conn,
        "2026-10-30",
        '[[observation]]\ntext = "drift adds volume"\nevidence = ["niggle:@knee"]\n'
        '[[observation]]\ntext = "sleep is steady"\n'
        '[[niggle]]\nkey = "knee"\nsite = "left knee"\ndate = 2026-10-29\nstatus = "reported"\n'
        'constraints = [{ kind = "rpe_cap", pattern = "squat", value = 7 }]\n',
    )
    checked_in(conn, "2026-11-06", '[[observation]]\nretire = "o-0001"\nbecause = "it stopped"\n')
    return conn


def test_ledger_lists_observations_with_their_retirement() -> None:
    conn = observations_raised_and_one_retired()

    result = ledger(conn, kind="observation", id_=None, open_=False, today=TODAY, last=10)

    assert [(r["id"], r["retired_at"], r["retired_because"]) for r in result.rows] == [
        ("o-0002", None, None),
        ("o-0001", "2026-11-06", "it stopped"),
    ]
    assert result.rows[1]["evidence"] == ["niggle:n-0001"]
    assert result.rows[0]["evidence"] == []


def test_ledger_open_keeps_only_current_observations() -> None:
    conn = observations_raised_and_one_retired()

    result = ledger(conn, kind="observation", id_=None, open_=True, today=TODAY, last=10)

    assert [r["id"] for r in result.rows] == ["o-0002"]


def test_ledger_by_id_finds_an_observation() -> None:
    conn = observations_raised_and_one_retired()

    result = ledger(conn, kind=None, id_="o-0001", open_=False, today=TODAY, last=10)

    assert [(r["record_kind"], r["text"]) for r in result.rows] == [
        ("observation", "drift adds volume")
    ]


def test_ledger_needs_a_kind_or_an_id() -> None:
    with pytest.raises(Invalid):
        ledger(a_store(), kind=None, id_=None, open_=False, today=TODAY, last=10)


def test_ledger_names_an_unknown_record_kind() -> None:
    with pytest.raises(Invalid) as raised:
        ledger(a_store(), kind="nigle", id_=None, open_=False, today=TODAY, last=10)

    assert "nigle" in raised.value.message


def a_library() -> Connection:
    conn = a_store()
    an_exercise(
        conn,
        "rdl",
        name="Romanian Deadlift",
        pattern="hinge",
        muscles={"primary": ["hamstrings", "glutes"], "secondary": ["lower_back"]},
        hevy_template_id="2B4B7310",
    )
    an_exercise(conn, "bb_bench_press", name="Bench Press (Barbell)")
    an_exercise(
        conn,
        "db_bench_press",
        name="Bench Press (Dumbbell)",
        load_mode="per_hand_x2",
        equipment_kind="dumbbell",
        source="draft",
    )
    an_exercise(
        conn,
        "bb_back_squat",
        name="Squat (Barbell)",
        pattern="squat",
        muscles={"primary": ["quads", "glutes"], "secondary": ["hamstrings"]},
    )
    return conn


def library_ids(**filters: Any) -> list[str]:
    arguments: dict[str, Any] = {"match": None, "patterns": (), "muscles": (), "last": 10}
    result = exercises(a_library(), **{**arguments, **filters})
    return [str(row["id"]) for row in result.rows]


def test_exercises_lists_every_library_row_by_id_with_its_eight_fields() -> None:
    result = exercises(a_library(), match=None, patterns=(), muscles=(), last=10)

    assert [row["id"] for row in result.rows] == [
        "bb_back_squat",
        "bb_bench_press",
        "db_bench_press",
        "rdl",
    ]
    assert result.rows[3] == {
        "id": "rdl",
        "name": "Romanian Deadlift",
        "load_mode": "total",
        "equipment_kind": "barbell",
        "pattern": "hinge",
        "muscles": {"primary": ["hamstrings", "glutes"], "secondary": ["lower_back"]},
        "hevy_template_id": "2B4B7310",
        "source": "catalogue",
    }
    assert (result.count, result.truncated) == (4, False)


def test_exercises_match_is_a_case_insensitive_substring_of_the_id_or_name() -> None:
    assert library_ids(match="BENCH") == ["bb_bench_press", "db_bench_press"]
    assert library_ids(match="romanian") == ["rdl"]


def test_exercises_with_two_patterns_keep_either() -> None:
    assert library_ids(patterns=("hinge", "squat")) == ["bb_back_squat", "rdl"]


def test_exercises_with_a_muscle_keep_rows_naming_it_primary_or_secondary() -> None:
    assert library_ids(muscles=("hamstrings",)) == ["bb_back_squat", "rdl"]
    assert library_ids(muscles=("lower_back", "chest")) == [
        "bb_bench_press",
        "db_bench_press",
        "rdl",
    ]


def test_exercises_filters_combine_as_and() -> None:
    assert library_ids(match="bb", muscles=("hamstrings",)) == ["bb_back_squat"]
    assert library_ids(match="bench", patterns=("hinge",)) == []


def test_exercises_with_an_unknown_pattern_or_muscle_return_no_rows_not_an_error() -> None:
    conn = a_library()

    by_pattern = exercises(conn, match=None, patterns=("balance",), muscles=(), last=10)
    by_muscle = exercises(conn, match=None, patterns=(), muscles=("tibialis",), last=10)

    assert (by_pattern.rows, by_pattern.count, by_pattern.truncated) == ([], 0, False)
    assert (by_muscle.rows, by_muscle.count) == ([], 0)


def test_exercises_keep_the_first_n_by_id_and_say_more_exist() -> None:
    capped = exercises(a_library(), match=None, patterns=(), muscles=(), last=2)
    full = exercises(a_library(), match=None, patterns=(), muscles=(), last=None)

    assert [row["id"] for row in capped.rows] == ["bb_back_squat", "bb_bench_press"]
    assert (capped.count, capped.truncated) == (4, True)
    assert (len(full.rows), full.truncated) == (4, False)
