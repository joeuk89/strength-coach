"""The example `coach schema <verb>` shows is a Draft the verb takes: its dry run on a store
holding the exercise library raises no violation."""

from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.programs import a_config, a_goal, a_library_store

from coach.core.draft_kinds.goal import GOAL
from coach.core.draft_kinds.ledger import CHECK_IN, RECORD
from coach.core.draft_kinds.program import PROGRAM
from coach.services.checkin_record import checkin_record
from coach.services.goal_adopt import goal_adopt
from coach.services.program import adopt
from coach.services.record import record

CLOCK = FixedClock()


def test_the_program_example_adopts_with_no_violation() -> None:
    conn = a_library_store()
    a_goal(conn, "strength", ("bb_bench_press",))

    result = adopt(
        conn,
        PROGRAM.example.encode(),
        file="draft.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=CLOCK,
        dry_run=True,
    )

    assert result.dry_run
    assert [s["id"] for s in result.sessions] == ["upper"]


def test_the_goal_example_adopts() -> None:
    result = goal_adopt(
        a_library_store(), GOAL.example.encode(), file="draft.toml", clock=CLOCK, dry_run=True
    )

    assert result.kind == "strength"


def test_the_ledger_example_records() -> None:
    result = record(
        a_library_store(), RECORD.example.encode(), file="draft.toml", clock=CLOCK, dry_run=True
    )

    assert list(result.ids) == ["weigh_in"]


def test_the_check_in_example_records() -> None:
    result = checkin_record(
        a_library_store(), CHECK_IN.example.encode(), file="draft.toml", clock=CLOCK, dry_run=True
    )

    assert result.check_in
