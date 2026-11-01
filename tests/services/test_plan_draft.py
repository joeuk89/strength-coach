import datetime

import pytest
from support.clock import FixedClock
from support.history import a_status_span
from support.kit_fixtures import kit_files
from support.ledger import an_exercise
from support.plans import a_note, a_squat_program, an_approved_plan, squat_logged
from support.programs import a_config, the_worked_store

from coach.core.errors import Invalid, Setup
from coach.core.kit import KitFiles
from coach.core.plan_draft import AthleteNote
from coach.core.planned_week import RotationPosition
from coach.services.plan_draft import PlanDraftResult, plan_draft
from coach.services.record import record
from coach.store.connection import Connection

NEXT_MONDAY = datetime.date(2026, 11, 2)


def drafted(
    conn: Connection,
    week: datetime.date | None = NEXT_MONDAY,
    *,
    kits: tuple[KitFiles, ...] | None = None,
) -> PlanDraftResult:
    return plan_draft(
        conn,
        config=a_config(),
        kits=(kit_files(),) if kits is None else kits,
        clock=FixedClock(),
        week=week,
    )


def test_the_worked_squat_hit_moves_one_rack_row_from_the_imported_history() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", (120, 8, 7.5), (120, 8, 8), (120, 8, 8), (120, 8, 8))

    draft = drafted(conn).draft

    [session] = draft.sessions
    assert (session.session.session_id, session.session.date) == ("lower", NEXT_MONDAY)
    [line] = session.lines
    assert line.change == "4×6–8 @8: 120 → 125"
    assert line.derived_from == "exposure:h-1/bb_back_squat"
    assert draft.position == RotationPosition("A", "program_adopt")
    assert [flag.code for flag in draft.flags] == ["rotation_unconfirmed"]


def test_with_no_history_the_line_opens_at_its_start_load() -> None:
    line = drafted(a_squat_program()).draft.sessions[0].lines[0]

    assert (line.derived_from, line.change) == ("start_load", "first prescription")
    assert line.groups[-1].load is not None and line.groups[-1].load.amount == 100


def test_the_draft_text_is_the_rendered_draft() -> None:
    result = drafted(a_squat_program())

    assert 'change = "first prescription"' in result.text
    assert result.text == drafted(a_squat_program()).text


def test_the_default_week_is_this_week_while_it_has_no_approved_plan() -> None:
    conn = a_squat_program()

    assert drafted(conn, None).draft.week == datetime.date(2026, 10, 26)
    an_approved_plan(conn, "2026-10-26")
    assert drafted(conn, None).draft.week == NEXT_MONDAY


def test_a_week_that_is_not_a_monday_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        drafted(a_squat_program(), datetime.date(2026, 11, 3))

    assert raised.value.code == "invalid_argument"


def test_with_no_version_adopted_there_is_nothing_to_draft() -> None:
    with pytest.raises(Invalid) as raised:
        drafted(the_worked_store())

    assert raised.value.code == "state_conflict"


def test_a_position_outside_the_rotation_is_refused() -> None:
    with pytest.raises(Invalid) as raised:
        plan_draft(
            a_squat_program(),
            config=a_config(),
            kits=(kit_files(),),
            clock=FixedClock(),
            week=NEXT_MONDAY,
            position="Z",
        )

    assert "'Z'" in raised.value.message
    assert raised.value.code == "state_conflict"


def test_stale_kit_tables_stop_the_draft() -> None:
    stale = kit_files(inventory_sha256="0" * 64)

    with pytest.raises(Setup) as raised:
        drafted(a_squat_program(), kits=(stale,))

    assert raised.value.code == "kit_tables_stale"


def test_the_position_follows_the_last_plan_and_a_superseding_draft_keeps_its_own() -> None:
    conn = a_squat_program(
        schedule={"rotation": ["A", "B"], "A": {"mon": "lower"}, "B": {"wed": "lower"}}
    )
    an_approved_plan(conn, "2026-10-26", "A")

    after = drafted(conn).draft
    plan_id = an_approved_plan(conn, "2026-11-02", "B")
    superseding = drafted(conn).draft

    assert after.position == RotationPosition("B", "previous_plan")
    assert after.sessions[0].session.date == datetime.date(2026, 11, 4)
    assert after.supersedes is None
    assert superseding.position == RotationPosition("B", "plan_in_force")
    assert superseding.supersedes == plan_id


def test_the_draft_carries_every_note_since_the_last_approved_plan_verbatim() -> None:
    conn = a_squat_program()
    a_note(conn, "an-0001", "2026-10-20", "Before the plan.", at="2026-10-20T09:00:00+00:00")
    an_approved_plan(conn, "2026-10-26", approved_at="2026-10-25T18:00:00+00:00")
    a_note(
        conn,
        "an-0002",
        "2026-10-27",
        "Squat felt heavy.",
        about="exercise:bb_back_squat",
        at="2026-10-27T09:00:00+00:00",
    )

    draft = drafted(conn).draft

    assert draft.notes == (
        AthleteNote(datetime.date(2026, 10, 27), "Squat felt heavy.", "exercise:bb_back_squat"),
    )


def test_with_no_approved_plan_every_note_is_carried() -> None:
    conn = a_squat_program()
    a_note(conn, "an-0001", "2026-10-20", "First.", at="2026-10-20T09:00:00+00:00")

    assert [note.text for note in drafted(conn).draft.notes] == ["First."]


def test_an_open_niggles_rehab_session_is_planned_and_a_resolved_ones_is_not() -> None:
    conn = a_squat_program()
    an_exercise(conn, "band_external_rotation", load_mode="band", equipment_kind="band")
    rehab = """
[[niggle]]
site = "left shoulder"
date = 2026-10-24
status = "reported"

[niggle.rehab]
session = "shoulder_rehab"
title = "Shoulder rehab"
cadence = "standing"

[[niggle.rehab.line]]
exercise = "band_external_rotation"
rest_s = 30

[[niggle.rehab.line.sets]]
count = 2
reps = 15
"""
    record(conn, rehab.encode(), file="n.toml", clock=FixedClock())

    sessions = drafted(conn).draft.sessions

    assert [(s.session.session_id, s.session.kind) for s in sessions] == [
        ("lower", "lifting"),
        ("shoulder_rehab", "rehab"),
    ]
    resolved = '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-29\nstatus = "resolved"\n'
    record(conn, resolved.encode(), file="r.toml", clock=FixedClock())
    assert [s.session.session_id for s in drafted(conn).draft.sessions] == ["lower"]


def test_a_no_training_span_over_the_whole_week_plans_nothing() -> None:
    conn = a_squat_program()
    a_status_span(conn, "ss-0001", "no_training", "2026-11-01", "2026-11-09")

    assert drafted(conn).draft.sessions == ()


def test_a_return_line_after_43_days_off_derives_the_same_load_twice_from_one_store() -> None:
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-09-14", (120, 8, 8), (120, 8, 8), (120, 7, 8), (120, 6, 8))

    first, second = (drafted(conn).draft.sessions[0].lines[0] for _ in range(2))

    assert first.steps[0].cause == "return 43+, 49 days off"
    assert first.groups[-1].load is not None and first.groups[-1].load.amount == 100
    assert (second.groups, second.steps) == (first.groups, first.steps)
