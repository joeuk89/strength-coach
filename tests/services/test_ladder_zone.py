"""A rung's start is the day its Decision was recorded on in the athlete's timezone: recorded at
23:30 UTC on Monday, it starts on Monday in UTC and on Tuesday in Tokyo, so Monday's exposure
counts toward the rung only in UTC."""

import datetime
from typing import cast
from zoneinfo import ZoneInfo

from support.check_in_cards import field_of
from support.clock import FixedClock
from support.ladders import a_ladder_program, ladder_rung_decision, logged
from support.programs import a_config

from coach.core.check_in_card import ladder_row
from coach.services.checkin_open import checkin_open
from coach.services.progress import progress
from coach.services.publish import publish
from coach.services.record import record
from coach.store.connection import Connection

TOKYO = ZoneInfo("Asia/Tokyo")
FIRST_SUNDAY = datetime.date(2026, 11, 8)
LATE_MONDAY = datetime.datetime(2026, 11, 2, 23, 30, tzinfo=datetime.UTC)


def a_rung_recorded_late_on_monday() -> Connection:
    conn = a_ladder_program()
    record(conn, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock(LATE_MONDAY))
    logged(conn, "ab_wheel", "2026-11-02", 8)
    return conn


def test_progress_dates_the_rung_in_the_zone_it_is_given() -> None:
    conn = a_rung_recorded_late_on_monday()

    exposures = [
        ladder_row(row)["exposures"]
        for zone in (datetime.UTC, TOKYO)
        for row in progress(
            conn, on=FIRST_SUNDAY, units="lb", bodyweight_units="kg", zone=zone
        ).ladders
    ]

    assert exposures == [1, 0]


def test_the_published_progress_page_dates_the_rung_in_the_zone_it_is_given() -> None:
    conn = a_rung_recorded_late_on_monday()

    pages = [
        publish(conn, engine_version="0.4.0", config=a_config(), zone=zone).pages[
            "pages/progress.md"
        ]
        for zone in (datetime.UTC, TOKYO)
    ]

    assert "| 1 of 2 | no |" in pages[0]
    assert "| 0 of 2 | no |" in pages[1]


def test_the_check_in_card_dates_the_rung_in_the_clocks_zone() -> None:
    conn = a_rung_recorded_late_on_monday()

    cards = [
        checkin_open(
            conn,
            FixedClock(datetime.datetime(2026, 11, 8, 12, tzinfo=zone)),
            units="lb",
            bodyweight_units="kg",
        )
        for zone in (datetime.UTC, TOKYO)
    ]

    rows = [
        cast("list[dict[str, object]]", field_of(card, "ladders").facts["rows"]) for card in cards
    ]
    assert [row["exposures"] for [row] in rows] == [1, 0]
