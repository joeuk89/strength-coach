import datetime

from support.check_in_cards import field_of, opened
from support.clock import FixedClock
from support.ladders import a_ladder_program, ladder_rung_decision, logged
from support.pages import the_pages
from support.plans import a_squat_program
from support.program_drafts import a_ladder_line, a_rung

from coach.core.check_in_card import ladder_row
from coach.services.progress import progress
from coach.services.record import record

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
