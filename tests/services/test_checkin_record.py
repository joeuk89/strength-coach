import datetime

import pytest
from support.clock import FixedClock
from support.ledger import a_hevy_workout, a_store, an_exercise

from coach.core.errors import Invalid
from coach.services.checkin_record import CheckInRecordResult, checkin_record
from coach.store.connection import Connection

WORKOUT = "b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13"
NOV_1 = datetime.datetime(2026, 11, 1, 18, 0, tzinfo=datetime.UTC)


def header(date: str = "2026-11-01", read: str = "a steady week", tier: str = "light") -> str:
    return f'date = {date}\ntier = "{tier}"\nread = "{read}"\n'


EVERY_KIND = (
    header(tier="deep")
    + f"""readiness = "ok"
window_start = 2026-10-26

[phase]
kind = "maintenance"
until = {{ kind = "coachs_call" }}
because = "recomp"

[[niggle]]
key = "hamstring"
site = "hamstring after runs"
date = 2026-11-01
status = "easing"
constraints = [{{ kind = "rpe_cap", pattern = "hinge", value = 7 }}]

[[followup]]
text = "retest the pull-up"
raised = 2026-11-01
due = 2026-11-29

[[decision]]
kind = "activity_cap"
activity_kind = "run"
weekly_distance = 17
because = "pain"
text = "runs capped while the hamstring settles"
evidence = ["niggle:@hamstring"]

[[annotation]]
kind = "void"
target = "workout:{WORKOUT}"
because = "coach_judgement"

[[note]]
date = 2026-10-31
text = "slept badly before the Friday session"

[[workout]]
date = 2026-10-28
title = "PT session"
minutes = 60

[[weigh_in]]
date = 2026-11-01
kg = 82.4

[[sleep_night]]
night = 2026-10-31
hours = 6.5

[[activity]]
date = 2026-10-29
kind = "run"
minutes = 30
rpe = 6
quality = false

[[status_span]]
kind = "travel"
from_date = 2026-11-10

[[exercise]]
id = "bb_bench_press"
hevy_title = "Bench Press (Barbell)"

[[observation]]
text = "drift adds volume"
evidence = ["niggle:@hamstring"]
"""
)
STAMPED = (
    "niggle_event",
    "follow_up",
    "follow_up_event",
    "decision",
    "annotation",
    "athlete_note",
    "workout",
    "weigh_in",
    "sleep_night",
    "activity",
    "status_span",
    "observation",
)


def run(conn: Connection, text: str, clock: FixedClock | None = None) -> CheckInRecordResult:
    return checkin_record(
        conn, text.encode("utf-8"), file="ci.toml", clock=clock or FixedClock(NOV_1)
    )


def a_store_with_a_workout() -> Connection:
    conn = a_store()
    an_exercise(conn, "bb_bench_press", hevy_template_id="AAAA0001")
    a_hevy_workout(conn, WORKOUT, templates=(("AAAA0001", "Bench Press (Barbell)"),))
    return conn


def check_ins(conn: Connection) -> list[tuple[str, str, str, str, str | None]]:
    return conn.execute(
        "SELECT id, window_start, window_end, status, superseded_by FROM check_in ORDER BY id"
    ).fetchall()


def test_a_file_with_every_kind_writes_the_row_and_stamps_each_record_with_it() -> None:
    conn = a_store_with_a_workout()

    result = run(conn, EVERY_KIND)

    assert (result.check_in, result.tier, result.superseded) == ("ci-2026-11-01", "deep", None)
    assert (result.window_start, result.window_end) == (
        datetime.date(2026, 10, 26),
        datetime.date(2026, 11, 1),
    )
    assert result.ids["observation"] == ["o-0001"]
    assert result.ids["decision"] == ["d-0001"]
    assert result.phase_opened == "ph-0001"
    for table in STAMPED:
        stamps = {
            s
            for (s,) in conn.execute(
                f"SELECT check_in FROM {table} WHERE draft_hash = ?", (result.draft_hash,)
            )
        }
        assert stamps == {"ci-2026-11-01"}, table
    assert conn.execute("SELECT readiness, read FROM check_in").fetchone() == (
        "ok",
        "a steady week",
    )
    assert conn.execute("SELECT opened, opened_by FROM phase").fetchone() == (
        "2026-11-01",
        "check_in:ci-2026-11-01",
    )
    assert conn.execute("SELECT raised, text, evidence FROM observation").fetchone() == (
        "2026-11-01",
        "drift adds volume",
        '["niggle:n-0001"]',
    )
    sources = {
        s
        for (s,) in conn.execute("SELECT source FROM weigh_in UNION SELECT source FROM sleep_night")
    }
    assert sources == {"check_in"}


def test_a_bad_record_leaves_nothing_written_not_even_the_row() -> None:
    conn = a_store()

    with pytest.raises(Invalid):
        run(conn, header() + '[[note]]\ndate = 2026-11-01\ntext = "x"\nabout = "niggle:n-0009"\n')

    assert check_ins(conn) == []


def test_the_same_file_again_writes_nothing_and_returns_the_same_row() -> None:
    conn = a_store_with_a_workout()

    first = run(conn, EVERY_KIND)
    second = run(conn, EVERY_KIND)

    assert second == first
    assert len(check_ins(conn)) == 1


def test_the_second_row_starts_the_day_after_the_firsts_window_end() -> None:
    conn = a_store()
    run(conn, header() + "window_start = 2026-10-26\n")

    second = run(conn, header("2026-11-08"))

    assert (second.window_start, second.window_end) == (
        datetime.date(2026, 11, 2),
        datetime.date(2026, 11, 8),
    )


def test_a_second_file_setting_window_start_is_refused() -> None:
    conn = a_store()
    run(conn, header() + "window_start = 2026-10-26\n")

    with pytest.raises(Invalid):
        run(conn, header("2026-11-08") + "window_start = 2026-11-02\n")

    assert len(check_ins(conn)) == 1


def test_a_changed_read_for_the_same_date_supersedes_and_the_first_files_weigh_in_stays() -> None:
    conn = a_store()
    run(conn, header() + "window_start = 2026-10-26\n[[weigh_in]]\ndate = 2026-11-01\nkg = 82.4\n")

    corrected = run(conn, header(read="a better week") + "window_start = 2026-10-26\n")

    assert corrected.check_in == "ci-2026-11-01-2"
    assert corrected.superseded == "ci-2026-11-01"
    assert check_ins(conn) == [
        ("ci-2026-11-01", "2026-10-26", "2026-11-01", "superseded", "ci-2026-11-01-2"),
        ("ci-2026-11-01-2", "2026-10-26", "2026-11-01", "current", None),
    ]
    assert conn.execute("SELECT id FROM weigh_in_current").fetchall() == [("wi-0001",)]

    withdrawn = run(conn, header(read="third time") + '[[weigh_in]]\nwithdraws = "wi-0001"\n')

    assert withdrawn.check_in == "ci-2026-11-01-3"
    assert conn.execute("SELECT id FROM weigh_in_current").fetchall() == []


def test_a_superseding_row_keeps_the_window_of_the_row_before_the_one_it_replaces() -> None:
    conn = a_store()
    run(conn, header() + "window_start = 2026-10-26\n")
    run(conn, header("2026-11-08"))

    corrected = run(conn, header("2026-11-08", read="again"))

    assert (corrected.window_start, corrected.superseded) == (
        datetime.date(2026, 11, 2),
        "ci-2026-11-08",
    )


def test_an_earlier_check_in_can_be_corrected_after_a_later_one() -> None:
    conn = a_store()
    run(conn, header() + "window_start = 2026-10-26\n")
    run(conn, header("2026-11-08"))

    corrected = run(conn, header(read="again") + "window_start = 2026-10-26\n")

    assert (corrected.check_in, corrected.superseded) == ("ci-2026-11-01-2", "ci-2026-11-01")
    assert (corrected.window_start, corrected.window_end) == (
        datetime.date(2026, 10, 26),
        datetime.date(2026, 11, 1),
    )


def test_a_correction_between_two_check_ins_starts_after_the_one_before_it() -> None:
    conn = a_store()
    run(conn, header() + "window_start = 2026-10-26\n")
    run(conn, header("2026-11-08"))
    run(conn, header("2026-11-15"))

    corrected = run(conn, header("2026-11-08", read="again"))

    assert (corrected.check_in, corrected.window_start, corrected.superseded) == (
        "ci-2026-11-08-2",
        datetime.date(2026, 11, 2),
        "ci-2026-11-08",
    )


def test_phase_close_closes_the_open_phase_with_the_check_in_as_closed_by() -> None:
    conn = a_store()
    run(conn, EVERY_KIND.split("[[niggle]]")[0])

    result = run(conn, header("2026-11-08") + '[phase]\nclose = true\nbecause = "done"\n')

    assert result.phase_closed == "ph-0001"
    assert conn.execute("SELECT closed, closed_by, closed_because FROM phase").fetchone() == (
        "2026-11-08",
        "check_in:ci-2026-11-08",
        "done",
    )


def test_opening_a_phase_beside_an_open_one_is_refused() -> None:
    conn = a_store()
    run(conn, EVERY_KIND.split("[[niggle]]")[0])

    with pytest.raises(Invalid) as raised:
        run(
            conn,
            header("2026-11-08")
            + '[phase]\nkind = "deficit"\nuntil = { kind = "coachs_call" }\nbecause = "cut"\n',
        )

    assert raised.value.code == "phase_already_open"
    assert len(check_ins(conn)) == 1


def test_closing_with_no_open_phase_is_refused() -> None:
    with pytest.raises(Invalid):
        run(a_store(), header() + '[phase]\nclose = true\nbecause = "done"\n')


def test_an_observation_is_retired_in_place_by_a_later_check_in() -> None:
    conn = a_store()
    run(conn, header() + '[[observation]]\ntext = "drift adds volume"\n')

    result = run(
        conn, header("2026-11-08") + '[[observation]]\nretire = "o-0001"\nbecause = "it stopped"\n'
    )

    assert result.ids == {"observation": ["o-0001"]}
    assert conn.execute(
        "SELECT retired_at, retired_because, retired_check_in FROM observation"
    ).fetchone() == ("2026-11-08", "it stopped", "ci-2026-11-08")


@pytest.mark.parametrize("target", ["o-0009", "o-0001"])
def test_retiring_an_unknown_or_retired_observation_is_refused(target: str) -> None:
    conn = a_store()
    run(conn, header() + '[[observation]]\ntext = "drift adds volume"\n')
    run(conn, header("2026-11-08") + '[[observation]]\nretire = "o-0001"\nbecause = "gone"\n')

    with pytest.raises(Invalid):
        run(conn, header("2026-11-15") + f'[[observation]]\nretire = "{target}"\nbecause = "x"\n')


def test_a_date_inside_the_previous_window_is_refused() -> None:
    conn = a_store()
    run(conn, header("2026-11-08") + "window_start = 2026-11-02\n")

    with pytest.raises(Invalid):
        run(conn, header("2026-11-05"))
