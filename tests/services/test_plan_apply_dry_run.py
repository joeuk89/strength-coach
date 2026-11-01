from typing import cast

import pytest
from support.clock import FixedClock
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import (
    a_folder,
    a_mapped_routine,
    a_squat_program,
    an_acknowledgement,
    an_approved_plan,
    squat_logged,
)
from support.programs import a_config

from coach.core.errors import Invalid
from coach.core.flag import Flag
from coach.core.hevy_actions import HevyActions, RoutineAction, TemplateCreate
from coach.services.plan_apply import DryRun, dry_run
from coach.services.record import record
from coach.store import exercises
from coach.store.connection import Connection

KNEE_CAP = """
[[niggle]]
site = "left knee"
date = 2026-10-29
status = "reported"

[[niggle.constraints]]
kind = "load_cap"
exercise = "bb_back_squat"
value = 100
"""
PIN_115 = """
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Hold the squat under the last top set."
"""


def run(conn: Connection, data: bytes, *, hevy: bool = False) -> DryRun:
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=hevy),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


OFFGRID = "offgrid_anchor_ignored@line:2026-11-02/lower/bb_back_squat"


def a_squat_week() -> Connection:
    """Last Monday's squat logged at 121 lb, off the rack: the plan warns
    `offgrid_anchor_ignored`."""
    conn = a_squat_program()
    squat_logged(conn, "h-1", "2026-10-26", *[(121, 8, 8)] * 4)
    return conn


def write(conn: Connection, text: str) -> None:
    record(conn, text.encode("utf-8"), file="r.toml", clock=FixedClock())


def test_one_violation_on_one_line_refuses_with_every_flag_and_the_fixed_fact_gives_a_hash() -> (
    None
):
    conn = a_squat_week()
    write(conn, KNEE_CAP)
    draft = a_plan_draft(conn, overrides=PIN_115)

    with pytest.raises(Invalid) as raised:
        run(conn, draft)

    assert raised.value.code == "recovery_ceiling_exceeded"
    reported = cast(list[dict[str, object]], raised.value.details["flags"])
    flagged = {(f["key"], f["severity"]) for f in reported}
    assert flagged == {
        ("recovery_ceiling_exceeded@line:2026-11-02/lower/bb_back_squat", "violation"),
        (OFFGRID, "warning"),
    }

    write(conn, '[[niggle]]\nniggle = "n-0001"\ndate = 2026-10-30\nstatus = "resolved"\n')
    fixed = run(conn, a_plan_draft(conn, overrides=PIN_115))

    assert fixed.write_plan_hash.startswith("sha256:")
    assert [f.code for f in fixed.flags if f.severity == "violation"] == []


def acknowledge(key: str, params_hash: str, because: str = 'because = "kit"\n') -> str:
    return (
        f'[[acknowledge]]\nflag = "{key}"\nparams_hash = "{params_hash}"\n{because}'
        'text = "The 121 was a mislabelled plate."\n'
    )


def offgrid(dry: DryRun) -> Flag:
    return next(f for f in dry.flags if f.key == OFFGRID)


def test_an_acknowledged_warning_is_left_until_its_params_change() -> None:
    conn = a_squat_week()
    raised = offgrid(run(conn, a_plan_draft(conn)))
    draft = a_plan_draft(conn, acknowledge=acknowledge(OFFGRID, raised.params_hash))

    left = offgrid(run(conn, draft))
    squat_logged(conn, "h-2", "2026-10-28", *[(122, 8, 8)] * 4)
    after = offgrid(run(conn, draft))

    assert raised.left is None
    assert left.left is not None
    assert (left.left.because, left.left.source) == ("kit", "weekplan")
    assert after.params["logged_load"] == 122
    assert after.left is None


def test_a_leave_warning_decision_in_force_leaves_the_warning_with_no_draft_entry() -> None:
    conn = a_squat_week()
    raised = offgrid(run(conn, a_plan_draft(conn)))
    write(
        conn,
        '[[decision]]\nkind = "leave_warning"\n'
        'flag = "offgrid_anchor_ignored@line:lower/bb_back_squat"\n'
        f'params_hash = "{raised.params_hash}"\nuntil = 2026-11-30\n'
        'because = "kit"\ntext = "The home bar reads 121 until the plates are relabelled."\n',
    )

    left = offgrid(run(conn, a_plan_draft(conn)))

    assert left.left is not None
    assert left.left.source == "decision"


def test_a_superseding_draft_inherits_no_acknowledgement_from_the_plan_in_force() -> None:
    conn = a_squat_week()
    raised = offgrid(run(conn, a_plan_draft(conn)))
    plan_id = an_approved_plan(conn, "2026-11-02")
    an_acknowledgement(conn, plan_id, OFFGRID, raised.params_hash)

    superseding = run(conn, a_plan_draft(conn))

    assert superseding.checked.draft.supersedes == plan_id
    assert offgrid(superseding).left is None


@pytest.mark.parametrize(
    ("key", "because"),
    [
        (OFFGRID, ""),
        ("recovery_ceiling_exceeded@line:2026-11-02/lower/bb_back_squat", 'because = "pain"\n'),
        ("scheme_off_emphasis@line:2026-11-02/lower/bb_back_squat", 'because = "pain"\n'),
    ],
    ids=["no because", "a violation", "an adopt warning"],
)
def test_an_acknowledgement_a_plan_cannot_take_is_refused(key: str, because: str) -> None:
    conn = a_squat_week()

    with pytest.raises(Invalid) as raised:
        run(conn, a_plan_draft(conn, acknowledge=acknowledge(key, "sha256:x", because)))

    assert raised.value.code == "invalid_argument"


def test_an_unconfirmed_position_is_rotation_unconfirmed() -> None:
    conn = a_squat_week()

    with pytest.raises(Invalid) as raised:
        run(conn, a_plan_draft(conn, confirmed=False))

    assert raised.value.code == "rotation_unconfirmed"


def hash_of(conn: Connection, data: bytes, *, hevy: bool = False) -> str:
    return run(conn, data, hevy=hevy).write_plan_hash


def test_editing_a_note_leaves_the_hash_and_editing_an_override_changes_it() -> None:
    conn = a_squat_week()
    plain = a_plan_draft(conn, overrides=PIN_115)
    noted = plain.replace(b"note = []\n", b"") + b'\n[[note]]\ndate = 2026-10-30\ntext = "Sore."\n'
    edited = plain.replace(b"load = 115", b"load = 110")

    assert hash_of(conn, noted) == hash_of(conn, plain)
    assert hash_of(conn, edited) != hash_of(conn, plain)


def test_new_history_changes_the_hash() -> None:
    conn = a_squat_week()
    draft = a_plan_draft(conn)
    before = hash_of(conn, draft)

    squat_logged(conn, "h-2", "2026-10-28", *[(125, 8, 8)] * 4)

    assert hash_of(conn, draft) != before


def test_a_mapped_routine_moved_in_the_mirror_changes_the_hash() -> None:
    conn = a_squat_week()
    a_mapped_routine(conn, "lower", "r-1", updated_at="2026-10-20T10:00:00Z")
    draft = a_plan_draft(conn, hevy=True)
    before = run(conn, draft, hevy=True)

    a_mapped_routine(conn, "lower", "r-1", updated_at="2026-10-31T10:00:00Z", mapped=False)

    assert before.actions.updates == (RoutineAction("lower", "r-1"),)
    assert hash_of(conn, draft, hevy=True) != before.write_plan_hash


def test_without_hevy_the_dry_run_lists_no_action_and_still_hashes() -> None:
    conn = a_squat_week()

    dry = run(conn, a_plan_draft(conn))

    assert dry.actions == HevyActions()
    assert dry.write_plan_hash.startswith("sha256:")


def test_the_first_push_creates_the_program_folder_and_one_routine_per_planned_session() -> None:
    conn = a_squat_week()

    actions = run(conn, a_plan_draft(conn, hevy=True), hevy=True).actions

    assert actions == HevyActions(folders=("Program",), creates=(RoutineAction("lower"),))


def test_an_exercise_with_no_template_id_but_its_columns_is_a_template_to_create() -> None:
    conn = a_squat_week()
    columns = {
        "hevy_title": "Back Squat (home)",
        "hevy_exercise_type": "weight_reps",
        "hevy_equipment": "barbell",
        "hevy_muscle_group": "quadriceps",
    }
    with conn:
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": None, **columns})

    actions = run(conn, a_plan_draft(conn, hevy=True), hevy=True).actions

    assert actions.templates == (TemplateCreate("bb_back_squat", "Back Squat (home)"),)


def test_an_exercise_with_no_template_id_and_no_columns_is_hevy_template_missing() -> None:
    conn = a_squat_week()
    with conn:
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": None})

    with pytest.raises(Invalid) as raised:
        run(conn, a_plan_draft(conn, hevy=True), hevy=True)
    without_hevy = run(conn, a_plan_draft(conn))

    assert raised.value.code == "hevy_template_missing"
    assert [f.code for f in without_hevy.flags if f.severity == "violation"] == []


def test_a_mapped_session_the_version_no_longer_has_is_retired_into_a_new_retired_folder() -> None:
    conn = a_squat_week()
    a_mapped_routine(conn, "lower", "r-1", updated_at="2026-10-20T10:00:00Z")
    a_mapped_routine(conn, "upper", "r-2", updated_at="2026-10-20T10:00:00Z")
    a_folder(conn, "program", "f-1")

    actions = run(conn, a_plan_draft(conn, hevy=True), hevy=True).actions

    assert actions == HevyActions(
        folders=("Retired",),
        updates=(RoutineAction("lower", "r-1"),),
        retires=(RoutineAction("upper", "r-2"),),
    )
