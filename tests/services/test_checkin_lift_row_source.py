"""The check-in card's lift row names the exposure its e1RM came from (check-in.md, "Views",
field 7)."""

import datetime
from collections.abc import Mapping
from typing import cast

from support.check_in_cards import field_of, opened
from support.closed_weeks import a_check_in, a_planned_squat_week, monday
from support.pages import the_pages
from support.plans import a_squat_program, squat_logged

from coach.store.connection import Connection

THURSDAY = (datetime.date.fromisoformat(monday(0)) + datetime.timedelta(days=3)).isoformat()
BEFORE = "2026-10-29"


def squat_row(conn: Connection) -> Mapping[str, object]:
    rows = cast(list[Mapping[str, object]], field_of(opened(conn), "lifts").facts["rows"])
    return next(r for r in rows if r["exercise"] == "bb_back_squat")


def a_heavy_session() -> Connection:
    """`lower` on Monday at 176 lb for 5 at RPE 8."""
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(176, 5, 8)] * 4)
    return conn


def a_heavy_session_then_a_light_one() -> Connection:
    """`a_heavy_session`, then an unplanned workout on Thursday at 110 lb."""
    conn = a_heavy_session()
    squat_logged(conn, "h-2", THURSDAY, *[(110, 5, 6)] * 4)
    return conn


def test_an_e1rm_from_the_older_heavier_exposure_names_it_beside_the_newer_top_set() -> None:
    row = squat_row(a_heavy_session_then_a_light_one())

    assert row["top_set"] == {
        "load": 110.0,
        "reps": 5,
        "rpe": 6.0,
        "date": THURSDAY,
        "session": None,
    }
    assert row["e1rm_from"] == {
        "exposure": "exposure:h-1/bb_back_squat",
        "date": monday(0),
        "session": "lower",
    }
    assert row["exposures"] == 2


def test_one_exposure_whose_top_set_gives_the_e1rm_is_its_source() -> None:
    row = squat_row(a_heavy_session())

    top = cast(Mapping[str, object], row["top_set"])
    assert row["e1rm_from"] == {
        "exposure": "exposure:h-1/bb_back_squat",
        "date": top["date"],
        "session": top["session"],
    }
    assert (top["date"], top["session"], row["exposures"]) == (monday(0), "lower", 1)


def test_an_e1rm_set_before_the_window_names_that_exposure_outside_it() -> None:
    conn = a_squat_program()
    a_planned_squat_week(conn, monday(0))
    squat_logged(conn, "h-0", BEFORE, *[(200, 5, 8)] * 4)
    squat_logged(conn, "h-1", monday(0), *[(150, 5, 8)] * 4)

    card = opened(conn)

    rows = cast(list[Mapping[str, object]], field_of(card, "lifts").facts["rows"])
    assert card.window.start > datetime.date.fromisoformat(BEFORE)
    assert rows[0]["e1rm_from"] == {
        "exposure": "exposure:h-0/bb_back_squat",
        "date": BEFORE,
        "session": None,
    }
    assert rows[0]["exposures"] == 1


def test_the_row_keeps_its_top_set_and_e1rm_figures() -> None:
    row = squat_row(a_heavy_session_then_a_light_one())

    top = cast(Mapping[str, object], row["top_set"])
    assert (top["load"], top["reps"], top["rpe"]) == (110.0, 5, 6.0)
    assert (row["e1rm"], row["e1rm_before"], row["priority"]) == (217.07, None, False)


def lifts_section(conn: Connection) -> str:
    a_check_in(conn, monday(0), "2026-11-08")
    page = the_pages(conn)["pages/check-ins/2026-11-08.md"]
    return page.split("## Lifts\n", 1)[1].split("\n## ", 1)[0]


def test_the_page_names_the_e1rm_source_where_it_is_not_the_top_sets_exposure() -> None:
    section = lifts_section(a_heavy_session_then_a_light_one())

    assert "| e1RM from |" in section
    assert section.rstrip().endswith(f"| Lower on {monday(0)} |")


def test_the_page_leaves_the_source_out_where_the_top_set_gave_the_e1rm() -> None:
    section = lifts_section(a_heavy_session())

    assert "Back Squat" in section
    assert "from" not in section
