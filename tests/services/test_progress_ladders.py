import datetime

from support.check_in_cards import field_of, opened
from support.clock import FixedClock, at
from support.ladders import a_ladder_program, ladder_rung_decision, logged
from support.pages import the_pages
from support.plans import a_squat_program
from support.program_drafts import a_ladder_line, a_rung

from coach.core.check_in_card import ladder_row
from coach.services.progress import progress
from coach.services.record import record
from coach.store.connection import Connection

FIRST_SUNDAY = datetime.date(2026, 11, 8)


def test_the_progress_view_carries_the_ladder_rows_the_check_in_card_shows() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)

    report = progress(conn, on=FIRST_SUNDAY, units="lb", bodyweight_units="kg", zone=datetime.UTC)

    assert [ladder_row(r) for r in report.ladders] == [
        {
            "session": "lower",
            "line": "dead_bug",
            "rung": 1,
            "exercise": "dead_bug",
            "rungs": 3,
            "exposures": 2,
            "needed": 2,
            "met": True,
            "held": False,
            "next": "ab_wheel",
        }
    ]
    assert [ladder_row(r) for r in report.ladders] == field_of(opened(conn), "ladders").facts[
        "rows"
    ]


def test_the_progress_page_prints_a_ladders_table() -> None:
    conn = a_ladder_program()
    logged(conn, "dead_bug", "2026-11-05", 10)

    page = the_pages(conn)["pages/progress.md"]

    assert (
        "## Ladders\n\n"
        "| line | standing rung | exposures toward the criterion | met |\n"
        "| --- | --- | --- | --- |\n"
        "| Lower: Dead Bug | 1 of 3, Dead Bug | 1 of 2 | no |"
    ) in page


def test_a_climbed_line_keeps_its_first_rungs_name_beside_the_standing_rungs() -> None:
    conn = a_ladder_program()
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock())

    page = the_pages(conn)["pages/progress.md"]

    assert "| Lower: Dead Bug | 2 of 3, Ab Wheel Rollout |" in page


def test_a_manual_rung_on_the_progress_page_reads_in_plain_words() -> None:
    manual = a_ladder_line(
        "dead_bug",
        a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}], advance={"manual": True}),
        a_rung("ab_wheel", sets=[{"count": 3, "reps": 8, "rpe": 8}]),
    )
    conn = a_ladder_program(manual)

    page = the_pages(conn)["pages/progress.md"]

    assert "| Lower: Dead Bug | 1 of 2, Dead Bug | when you and the coach agree | no |" in page


def test_a_progress_page_with_no_ladder_line_prints_no_ladders_table() -> None:
    conn = a_squat_program()

    assert "## Ladders" not in the_pages(conn)["pages/progress.md"]


TEMPO_LADDER = a_ladder_line(
    "dead_bug",
    a_rung(sets=[{"count": 3, "reps": 10, "rpe": 8}], cues="lower for 4 s"),
    a_rung("dead_bug", sets=[{"count": 3, "reps": 10, "rpe": 8}], cues="lower for 6 s"),
    a_rung("dead_bug", sets=[{"count": 3, "reps": 10, "rpe": 8}], cues="lower for 8 s"),
)


def a_read_of(conn: Connection, on: datetime.date) -> dict[str, object]:
    report = progress(conn, on=on, units="lb", bodyweight_units="kg", zone=datetime.UTC)
    [row] = [ladder_row(r) for r in report.ladders]
    return {key: row[key] for key in ("rung", "exposures", "met")}


def climbed_to_rung_2_on(conn: Connection, on: datetime.date) -> None:
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock(at(on)))


def test_a_ladder_of_three_rungs_on_one_exercise_adopts_and_stands_on_the_first() -> None:
    conn = a_ladder_program(TEMPO_LADDER)

    assert a_read_of(conn, FIRST_SUNDAY) == {"rung": 1, "exposures": 0, "met": False}


def test_exposures_before_the_climb_count_for_nothing_on_a_shared_exercise() -> None:
    conn = a_ladder_program(TEMPO_LADDER)
    logged(conn, "dead_bug", "2026-11-02", 10)
    logged(conn, "dead_bug", "2026-11-05", 10)
    climbed_to_rung_2_on(conn, datetime.date(2026, 11, 6))

    assert a_read_of(conn, FIRST_SUNDAY) == {"rung": 2, "exposures": 0, "met": False}


def test_the_criterion_met_from_the_rungs_start_offers_the_climb_on_a_shared_exercise() -> None:
    conn = a_ladder_program(TEMPO_LADDER)
    logged(conn, "dead_bug", "2026-11-02", 10)
    climbed_to_rung_2_on(conn, datetime.date(2026, 11, 3))
    logged(conn, "dead_bug", "2026-11-05", 10)
    logged(conn, "dead_bug", "2026-11-07", 10)

    assert a_read_of(conn, FIRST_SUNDAY) == {"rung": 2, "exposures": 2, "met": True}
