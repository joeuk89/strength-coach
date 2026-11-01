import datetime

from support.ledger import a_hevy_workout, a_store, an_exercise
from support.program_drafts import a_draft, a_line, a_session, toml

from coach.core.program.parse import parse_program_draft
from coach.store import exercises, programs, workouts
from coach.store.connection import Connection


def a_version(conn: Connection, sequence: int, kind: str = "redesign") -> programs.VersionRow:
    draft = a_draft(a_session("push", a_line(), a_line("db_curl")), kind=kind)
    form = parse_program_draft(toml(draft), file="d.toml").form
    row = programs.VersionRow(
        id=f"pv-{sequence}",
        sequence=sequence,
        position="A",
        adopted=f"2026-11-0{sequence}",
        form=form,
        draft_hash=f"sha256:{sequence}",
        recorded_at="2026-11-01T12:00:00+00:00",
    )
    with conn:
        programs.insert_version(conn, row)
    return row


def test_a_version_round_trips_with_its_sessions_and_lines() -> None:
    conn = a_store()
    an_exercise(conn, "bb_bench_press")
    an_exercise(conn, "db_curl")

    written = a_version(conn, 1)

    assert programs.latest(conn) == written
    assert programs.line_counts(conn, "pv-1") == [("push", 2)]
    assert conn.execute("SELECT id, introduced_in FROM session").fetchall() == [("push", "pv-1")]


def test_a_session_keeps_the_version_that_first_named_it() -> None:
    conn = a_store()
    an_exercise(conn, "bb_bench_press")
    an_exercise(conn, "db_curl")
    a_version(conn, 1)

    a_version(conn, 2, kind="amend")

    latest = programs.latest(conn)
    assert latest is not None and latest.sequence == 2
    assert conn.execute("SELECT introduced_in FROM session").fetchall() == [("pv-1",)]


def test_the_block_opens_at_the_latest_redesign() -> None:
    conn = a_store()
    an_exercise(conn, "bb_bench_press")
    an_exercise(conn, "db_curl")
    a_version(conn, 1)
    a_version(conn, 2, kind="amend")

    assert programs.block_opened(conn) == "2026-11-01"
    a_version(conn, 3)
    assert programs.block_opened(conn) == "2026-11-03"


def test_an_exercise_has_an_exposure_when_a_current_workout_logs_its_template() -> None:
    conn = a_store()
    an_exercise(conn, "bb_bench_press", hevy_template_id="T-BENCH")
    an_exercise(conn, "db_curl", hevy_template_id="T-CURL")
    a_hevy_workout(conn, "w1", date=datetime.date(2026, 10, 20), templates=(("T-BENCH", "Bench"),))

    assert workouts.exercises_with_exposure(conn) == frozenset({"bb_bench_press"})


def test_a_declared_exercise_is_inserted_from_the_draft_or_updated_field_by_field() -> None:
    conn = a_store()
    an_exercise(conn, "db_curl", hevy_template_id="T-CURL", name="Curl")
    with conn:
        exercises.upsert_declared(conn, "db_curl", {"hevy_title": "Bicep Curl (Dumbbell)"})
        exercises.upsert_declared(
            conn,
            "custom_ring_push_up",
            {
                "name": "Ring push-up",
                "load_mode": "bodyweight",
                "equipment_kind": "bodyweight",
                "pattern": "horizontal_push",
                "muscles": {"primary": ["chest"], "secondary": []},
            },
        )

    curl = exercises.get(conn, "db_curl")
    assert curl is not None
    assert (curl["name"], curl["hevy_title"], curl["hevy_template_id"]) == (
        "Curl",
        "Bicep Curl (Dumbbell)",
        "T-CURL",
    )
    ring = exercises.get(conn, "custom_ring_push_up")
    assert ring is not None
    assert (ring["source"], ring["hevy_template_id"]) == ("draft", None)
