import datetime

from coach.core.closed_week.block import Block, block_ceiling_exceeded, blocks
from coach.core.closed_week.kind import WeekKind

ADOPTED = datetime.date(2026, 10, 30)
FIRST = datetime.date(2026, 11, 2)


def weeks(*kinds: WeekKind) -> list[tuple[datetime.date, WeekKind]]:
    return [(FIRST + datetime.timedelta(weeks=n), kind) for n, kind in enumerate(kinds)]


def test_a_block_opens_at_a_redesign_and_counts_its_hard_weeks() -> None:
    assert blocks(weeks("hard", "hard"), [ADOPTED]) == (Block("b-2026-10-30", ADOPTED, 2, 2),)


def test_a_light_week_closes_the_block_and_the_next_hard_week_counts_1_in_a_new_one() -> None:
    found = blocks(weeks("hard", "hard", "light", "hard"), [ADOPTED])

    assert found == (
        Block("b-2026-10-30", ADOPTED, 2, 3, "light"),
        Block("b-2026-11-23", datetime.date(2026, 11, 23), 1, 1),
    )


def test_a_paused_or_partial_week_leaves_the_count_where_it_was() -> None:
    [block] = blocks(weeks("hard", "partial", "minimum", "break", "one_off", "hard"), [ADOPTED])

    assert block.hard_weeks == 2


def test_return_and_missed_weeks_close_the_block() -> None:
    found = blocks(weeks("hard", "return", "hard", "missed"), [ADOPTED])

    assert [(b.hard_weeks, b.closed_by) for b in found] == [(1, "return"), (1, "missed"), (0, None)]


def test_a_redesign_closes_the_open_block_and_opens_one_dated_at_adoption() -> None:
    redesign = datetime.date(2026, 11, 12)

    found = blocks(weeks("hard", "hard", "hard"), [ADOPTED, redesign])

    assert found == (
        Block("b-2026-10-30", ADOPTED, 2, 2, "redesign"),
        Block("b-2026-11-12", redesign, 1, 1),
    )


def test_a_redesign_right_after_a_closing_week_replaces_the_empty_block() -> None:
    redesign = datetime.date(2026, 11, 9)

    found = blocks(weeks("light", "hard"), [ADOPTED, redesign])

    assert [b.id for b in found] == ["b-2026-10-30", "b-2026-11-09"]


def test_weeks_before_the_first_version_count_in_no_block() -> None:
    assert blocks(weeks("hard"), []) == ()
    assert blocks(weeks("hard"), [datetime.date(2026, 11, 7)]) == (
        Block("b-2026-11-07", datetime.date(2026, 11, 7)),
    )


def test_the_count_reaching_the_ceiling_is_a_violation_on_the_plan() -> None:
    block = Block("b-2026-10-30", ADOPTED, 6, 6)
    monday = datetime.date(2026, 12, 14)

    flag = block_ceiling_exceeded(block, 6, monday)

    assert flag is not None and flag.key == "block_ceiling_exceeded@week:2026-12-14"
    assert flag.params == {"hard_weeks": 6, "ceiling": 6, "block_id": "b-2026-10-30"}
    assert block_ceiling_exceeded(Block("b-2026-10-30", ADOPTED, 5, 5), 6, monday) is None
