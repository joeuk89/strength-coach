import pytest
from support.clock import FixedClock
from support.ledger import a_hevy_workout, a_store, a_weigh_in, an_exercise

from coach.core.errors import Invalid
from coach.services.record import RecordResult, record
from coach.services.unmapped import exercise_unmapped
from coach.store.connection import Connection

SEVEN_KINDS = """
[[note]]
date = 2026-10-29
text = "left knee clicks on the way down"
about = "exercise:@hold"

[[weigh_in]]
date = 2026-10-29
kg = 82.4

[[sleep_night]]
night = 2026-10-28
hours = 6.5

[[activity]]
date = 2026-10-27
kind = "run"
minutes = 30
distance_km = 5.2
rpe = 6
quality = false

[[status_span]]
kind = "travel"
from_date = 2026-11-02
to_date = 2026-11-06

[[workout]]
date = 2026-10-13
title = "PT session"
minutes = 60
session_rpe = 9

[[exercise]]
id = "custom_hollow_hold"
key = "hold"
name = "Hollow hold"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "core"
muscles = {primary = ["abdominals"], secondary = []}
hevy_template_id = "A1B2C3D4-0000"
hevy_title = "Hollow Hold"
"""


def run(conn: Connection, text: str) -> RecordResult:
    return record(conn, text.encode("utf-8"), file="d.toml", clock=FixedClock())


def count(conn: Connection, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_a_draft_with_one_row_of_each_kind_writes_every_table_and_lists_ids_by_kind() -> None:
    conn = a_store()

    result = run(conn, SEVEN_KINDS)

    assert result.ids == {
        "note": ["an-0001"],
        "weigh_in": ["wi-0001"],
        "sleep_night": ["sn-0001"],
        "activity": ["ac-0001"],
        "status_span": ["ss-0001"],
        "workout": ["w-0001"],
        "exercise": ["custom_hollow_hold"],
    }
    assert conn.execute("SELECT about FROM athlete_note").fetchone() == (
        "exercise:custom_hollow_hold",
    )
    assert conn.execute("SELECT source FROM exercise").fetchone() == ("record",)


def test_every_row_carries_the_draft_hash_and_recorded_at() -> None:
    conn = a_store()

    result = run(conn, SEVEN_KINDS)

    for table in ("athlete_note", "weigh_in", "sleep_night", "activity", "status_span", "workout"):
        assert conn.execute(f"SELECT draft_hash, recorded_at FROM {table}").fetchall() == [
            (result.draft_hash, "2026-10-30T12:00:00+00:00")
        ]


def test_re_running_the_same_draft_writes_nothing_and_returns_the_same_ids() -> None:
    conn = a_store()
    first = run(conn, SEVEN_KINDS)

    second = run(conn, SEVEN_KINDS)

    assert second == first
    assert count(conn, "weigh_in") == 1
    assert count(conn, "workout") == 1


def test_a_differing_draft_appends_with_the_next_ids() -> None:
    conn = a_store()
    run(conn, "[[weigh_in]]\ndate = 2026-10-29\nkg = 82.4\n")

    result = run(conn, "[[weigh_in]]\ndate = 2026-10-30\nkg = 82.1\n")

    assert result.ids == {"weigh_in": ["wi-0002"]}


def test_a_weigh_in_withdrawn_and_re_entered_in_one_file_leaves_one_live_row() -> None:
    conn = a_store()
    a_weigh_in(conn, "2026-10-29", 28.4, id_="wi-0001")

    result = run(
        conn,
        '[[weigh_in]]\nwithdraws = "wi-0001"\n[[weigh_in]]\ndate = 2026-10-29\nkg = 82.4\n',
    )

    assert result.ids == {"weigh_in": ["wi-0002", "wi-0003"]}
    assert result.withdrawn == ["wi-0001"]
    assert conn.execute("SELECT id, kg FROM weigh_in_current").fetchall() == [("wi-0003", 82.4)]
    assert conn.execute(
        "SELECT date, kg, source FROM weigh_in WHERE id = 'wi-0002'"
    ).fetchone() == (
        "2026-10-29",
        28.4,
        "manual",
    )


def test_two_live_weigh_ins_for_one_date_and_source_are_reading_duplicate() -> None:
    conn = a_store()
    a_weigh_in(conn, "2026-10-29", 82.0, id_="wi-0001")

    with pytest.raises(Invalid) as raised:
        run(conn, "[[weigh_in]]\ndate = 2026-10-29\nkg = 82.4\n")

    assert raised.value.code == "reading_duplicate"
    assert "wi-0001" in raised.value.message
    assert count(conn, "weigh_in") == 1


def test_a_sleep_night_twice_in_one_file_is_reading_duplicate_and_writes_nothing() -> None:
    conn = a_store()

    with pytest.raises(Invalid) as raised:
        run(
            conn,
            '[[note]]\ndate = 2026-10-29\ntext = "x"\n'
            "[[sleep_night]]\nnight = 2026-10-28\nhours = 7\n"
            "[[sleep_night]]\nnight = 2026-10-28\nhours = 6\n",
        )

    assert raised.value.code == "reading_duplicate"
    assert count(conn, "athlete_note") == 0


def test_withdrawing_a_row_twice_is_refused() -> None:
    conn = a_store()
    a_weigh_in(conn, "2026-10-29", 82.0, id_="wi-0001")
    run(conn, '[[weigh_in]]\nwithdraws = "wi-0001"\n')

    with pytest.raises(Invalid) as raised:
        run(conn, '[[weigh_in]]\nwithdraws = "wi-0001"\n# again\n')

    assert raised.value.code == "state_conflict"


def test_withdrawing_a_withdrawal_is_refused() -> None:
    conn = a_store()
    a_weigh_in(conn, "2026-10-29", 82.0, id_="wi-0001")
    run(conn, '[[weigh_in]]\nwithdraws = "wi-0001"\n')

    with pytest.raises(Invalid) as raised:
        run(conn, '[[weigh_in]]\nwithdraws = "wi-0002"\n')

    assert raised.value.code == "state_conflict"


def test_withdrawing_a_status_span_copies_its_columns() -> None:
    conn = a_store()
    run(conn, '[[status_span]]\nkind = "ill"\nfrom_date = 2026-10-20\n')

    run(conn, '[[status_span]]\nwithdraws = "ss-0001"\n')

    assert conn.execute(
        "SELECT kind, from_date, withdraws FROM status_span WHERE id = 'ss-0002'"
    ).fetchone() == ("ill", "2026-10-20", "ss-0001")
    assert count(conn, "status_span_current") == 0


def test_an_exercise_row_sets_the_template_id_and_clears_exercise_unmapped() -> None:
    conn = a_store()
    an_exercise(conn, "custom_arch_hold", load_mode="duration")
    a_hevy_workout(conn, "hevy-1", templates=(("C0FFEE01", "Arch Hold"),))
    a_hevy_workout(
        conn,
        "hevy-1",
        templates=(("C0FFEE01", "Arch Hold"),),
        updated_at="2026-10-21T10:00:00+00:00",
    )
    a_hevy_workout(conn, "hevy-2", templates=(("C0FFEE01", "Arch Hold"), ("AAAA0001", "Bench")))
    an_exercise(conn, "bb_bench_press", hevy_template_id="AAAA0001")
    assert [flag.key for flag in exercise_unmapped(conn)] == [
        "exercise_unmapped@workout:hevy-1",
        "exercise_unmapped@workout:hevy-2",
    ]

    result = run(conn, '[[exercise]]\nid = "custom_arch_hold"\nhevy_template_id = "C0FFEE01"\n')

    assert result.ids == {"exercise": ["custom_arch_hold"]}
    assert exercise_unmapped(conn) == []
    assert conn.execute(
        "SELECT hevy_template_id, source FROM exercise WHERE id = 'custom_arch_hold'"
    ).fetchone() == ("C0FFEE01", "catalogue")


def test_an_exercise_edit_may_not_rename_an_existing_exercise() -> None:
    conn = a_store()
    an_exercise(conn, "custom_arch_hold")

    with pytest.raises(Invalid) as raised:
        run(conn, '[[exercise]]\nid = "custom_arch_hold"\nname = "Arch"\n')

    assert raised.value.code == "state_conflict"


def test_a_new_exercise_must_declare_every_library_column() -> None:
    conn = a_store()

    with pytest.raises(Invalid) as raised:
        run(conn, '[[exercise]]\nid = "custom_new"\nhevy_template_id = "T"\n')

    assert "name" in raised.value.message


def test_a_template_id_another_exercise_carries_is_refused() -> None:
    conn = a_store()
    an_exercise(conn, "a", hevy_template_id="T1")
    an_exercise(conn, "b")

    with pytest.raises(Invalid) as raised:
        run(conn, '[[exercise]]\nid = "b"\nhevy_template_id = "T1"\n')

    assert "a" in raised.value.message
    assert raised.value.code == "state_conflict"


def test_an_exercise_only_draft_re_runs_as_a_no_op() -> None:
    conn = a_store()
    text = SEVEN_KINDS[SEVEN_KINDS.index("[[exercise]]") :]
    first = run(conn, text)

    assert run(conn, text) == first


def test_a_manual_workout_with_sets_is_current_and_resolves_its_exercise_template() -> None:
    conn = a_store()
    an_exercise(conn, "bb_back_squat", hevy_template_id="D04AC939", hevy_title="Squat (Barbell)")

    result = run(
        conn,
        "[[workout]]\ndate = 2026-10-06\nminutes = 45\n"
        '[[workout.sets]]\nexercise = "bb_back_squat"\nweight_kg = 100\nreps = 5\nrpe = 8\n',
    )

    assert result.ids == {"workout": ["w-0001"]}
    assert conn.execute("SELECT id, source, date FROM workout_current").fetchall() == [
        ("w-0001", "manual", "2026-10-06")
    ]
    assert conn.execute(
        "SELECT hevy_template_id, hevy_title, set_type, weight_kg, reps FROM logged_set"
    ).fetchall() == [("D04AC939", "Squat (Barbell)", "working", 100.0, 5)]


def test_a_manual_set_on_an_exercise_with_no_template_is_refused() -> None:
    conn = a_store()
    an_exercise(conn, "custom_thing")

    with pytest.raises(Invalid) as raised:
        run(conn, '[[workout]]\ndate = 2026-10-06\n[[workout.sets]]\nexercise = "custom_thing"\n')

    assert raised.value.code == "hevy_template_missing"


def test_a_manual_set_on_an_exercise_the_library_lacks_is_an_unknown_exercise() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), '[[workout]]\ndate = 2026-10-06\n[[workout.sets]]\nexercise = "nope"\n')

    assert raised.value.code == "unknown_exercise"


def test_a_note_about_an_exercise_the_library_lacks_is_refused() -> None:
    conn = a_store()

    with pytest.raises(Invalid) as raised:
        run(conn, '[[note]]\ndate = 2026-10-29\ntext = "x"\nabout = "exercise:nope"\n')

    assert "exercise:nope" in raised.value.message


def test_a_note_about_a_stored_exercise_keeps_the_ref() -> None:
    conn = a_store()
    an_exercise(conn, "bb_bench_press")

    run(conn, '[[note]]\ndate = 2026-10-29\ntext = "x"\nabout = "exercise:bb_bench_press"\n')

    assert conn.execute("SELECT about FROM athlete_note").fetchone() == ("exercise:bb_bench_press",)


def test_ids_are_four_digits_after_the_highest_stored() -> None:
    conn = a_store()
    a_weigh_in(conn, "2026-10-01", 80.0, id_="wi-0041")

    result = run(conn, "[[weigh_in]]\ndate = 2026-10-29\nkg = 82.4\n")

    assert result.ids == {"weigh_in": ["wi-0042"]}


def test_withdrawing_a_reading_that_is_not_stored_is_an_unresolved_ref() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), '[[weigh_in]]\nwithdraws = "wi-0009"\n')

    assert raised.value.code == "draft_ref_unresolved"


def test_a_note_about_a_record_that_is_not_stored_is_an_unresolved_ref() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), '[[note]]\ndate = 2026-10-29\ntext = "x"\nabout = "exercise:nope"\n')

    assert raised.value.code == "draft_ref_unresolved"


def test_a_manual_workout_on_a_session_no_version_or_niggle_raised_is_an_unresolved_ref() -> None:
    with pytest.raises(Invalid) as raised:
        run(a_store(), '[[workout]]\ndate = 2026-10-06\nsession_id = "nope"\nminutes = 10\n')

    assert raised.value.code == "draft_ref_unresolved"
