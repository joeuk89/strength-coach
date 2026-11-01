"""The check-in record renderer (check-in.md, "The prose rule"): every number in the generated
sections equals a value derived from the store, and the read appears verbatim."""

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import cast

from support.check_in_cards import a_planned_two_session_week, a_two_session_program, opened
from support.closed_weeks import a_check_in, monday
from support.history import an_annotation
from support.pages import the_pages
from support.plans import squat_logged

from coach.store import rows
from coach.store.connection import Connection

READ = "A steady block."
NUMBER = re.compile(r"(?<![\w.\-:/])\d+(?:\.\d+)?(?![\w\-:/]|\.\d)")


def a_closed_first_week() -> Connection:
    conn = a_two_session_program()
    a_planned_two_session_week(conn, monday(0))
    squat_logged(conn, "h-1", monday(0), *[(120, 8, 8)] * 4)
    a_check_in(conn, monday(0), "2026-11-08", readiness="ok")
    return conn


def the_record(conn: Connection) -> str:
    return the_pages(conn)["pages/check-ins/2026-11-08.md"]


def generated(text: str) -> str:
    before, read, after = text.partition(READ)
    assert read == READ
    return before + after


def numbers_in(value: object) -> Iterator[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        yield float(value)
    elif isinstance(value, str):
        yield from (float(n) for n in NUMBER.findall(value))
    elif isinstance(value, Mapping):
        for item in cast(Mapping[str, object], value).values():
            yield from numbers_in(item)
    elif isinstance(value, Sequence):
        for item in cast(Sequence[object], value):
            yield from numbers_in(item)


def test_every_number_in_the_generated_sections_is_one_the_card_derives_from_the_store() -> None:
    conn = a_closed_first_week()
    card = opened(conn)
    derived = {n for f in card.fields for n in numbers_in(f.facts)}

    shown = {float(n) for n in NUMBER.findall(generated(the_record(conn)))}

    assert shown
    assert shown <= derived
    assert {120.0, 8.0} <= shown


def test_the_read_appears_verbatim_once() -> None:
    text = the_record(a_closed_first_week())

    assert text.count(READ) == 1
    assert f"\n{READ}\n" in text


def test_a_later_match_annotation_changes_the_generated_sections_and_not_the_read() -> None:
    conn = a_two_session_program()
    a_planned_two_session_week(conn, monday(0))
    squat_logged(conn, "h-1", "2026-11-03", *[(120, 8, 8)] * 4)
    a_check_in(conn, monday(0), "2026-11-08")
    before = the_record(conn)

    an_annotation(
        conn, "a-0001", "match", "workout:h-1", planned_session="planned_session:2026-11-02/lower"
    )
    after = the_record(conn)

    assert generated(after) != generated(before)
    assert "matched" in generated(after)
    assert after.partition(READ)[1] == before.partition(READ)[1] == READ


def test_only_current_check_ins_have_a_record() -> None:
    conn = a_closed_first_week()
    a_check_in(conn, "2026-11-09", "2026-11-15")
    with conn:
        rows.supersede(conn, "check_in", "ci-2026-11-08", "ci-2026-11-15")

    records = [path for path in the_pages(conn) if path.startswith("pages/check-ins/")]

    assert records == ["pages/check-ins/2026-11-15.md"]
