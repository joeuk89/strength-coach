import datetime
from collections import Counter
from typing import Any, cast

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import a_squat_program, squat_logged
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config

from coach.core.errors import Invalid, Refused
from coach.services.plan_apply import ApplyResult, apply, dry_run
from coach.services.program import adopt
from coach.services.status import status
from coach.store import exercises, mirrors, routine_map, week_plans
from coach.store.connection import Connection

BENCH_TEMPLATE = "BP-0001"


def a_squat_week(*sessions: dict[str, object]) -> Connection:
    conn = a_squat_program(*sessions)
    with conn:
        exercises.update(conn, "bb_bench_press", {"hevy_template_id": BENCH_TEMPLATE})
    squat_logged(conn, "h-1", "2026-10-26", *[(120, 8, 8)] * 4)
    return conn


def the_hash(conn: Connection, data: bytes, *, hevy: bool = True) -> str:
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=hevy),
        kits=(kit_files(),),
        clock=FixedClock(),
    ).write_plan_hash


def push(
    conn: Connection,
    hevy: FakeHevy | None,
    data: bytes,
    expect: str | None,
) -> ApplyResult:
    return apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=expect,
        config=a_config(hevy=hevy is not None),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def approved(conn: Connection, data: bytes, hevy: FakeHevy) -> ApplyResult:
    return push(conn, hevy, data, the_hash(conn, data))


def requests(hevy: FakeHevy) -> list[tuple[object, object]]:
    return [(line["method"], line["path"]) for line in hevy.audit if line["kind"] == "request"]


def test_a_clean_push_writes_the_plan_creates_the_folder_and_posts_one_verified_routine_per_session() -> (  # noqa: E501
    None
):
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)

    result = push(conn, hevy, data, digest)

    plan = week_plans.in_force(conn, "2026-11-02")
    assert plan is not None
    assert (plan["id"], plan["write_plan_hash"]) == ("wp-2026-11-02", digest)
    assert result.week_plan_id == "wp-2026-11-02"
    assert requests(hevy) == [
        ("POST", "/v1/routine_folders"),
        ("POST", "/v1/routines"),
        ("POST", "/v1/routines"),
    ]
    kinds = Counter(str(line["kind"]) for line in hevy.audit)
    assert kinds == {"request": 3, "response": 3, "verify": 2}
    assert [(o.session_id, o.outcome) for o in result.routines] == [
        ("lower", "verified"),
        ("upper", "verified"),
    ]
    assert {s: status for s, _, status in routine_map.every(conn)} == {
        "lower": "active",
        "upper": "active",
    }
    assert result.audit_lines == 8


def test_without_expect_the_push_is_refused_and_nothing_is_sent() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())

    with pytest.raises(Refused) as missing:
        push(conn, hevy, a_plan_draft(conn, hevy=True), None)
    with pytest.raises(Refused) as stale:
        push(conn, hevy, a_plan_draft(conn, hevy=True), "sha256:stale")

    assert (missing.value.code, stale.value.code) == ("expect_missing", "expect_mismatch")
    assert hevy.calls == []
    assert week_plans.in_force(conn, "2026-11-02") is None


PIN_115 = """
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Hold the squat under the last top set."
"""


def pushed(conn: Connection) -> FakeHevy:
    """The first week pushed: one verified routine for `lower`."""
    hevy = FakeHevy(FixedClock())
    approved(conn, a_plan_draft(conn, hevy=True), hevy)
    return hevy


def lower_routine(conn: Connection) -> str:
    return routine_map.mapped(conn)["lower"]


def test_a_routine_moved_in_hevy_refuses_the_whole_push_before_any_put() -> None:
    conn = a_squat_week()
    hevy = pushed(conn)
    hevy.move_routine(lower_routine(conn), "2026-10-31T09:00:00Z")
    hevy.calls.clear()
    data = a_plan_draft(conn, hevy=True, overrides=PIN_115)

    with pytest.raises(Refused) as moved:
        approved(conn, data, hevy)

    assert moved.value.code == "routine_moved"
    assert [method for method, _ in hevy.calls] == ["GET"]
    plan = week_plans.in_force(conn, "2026-11-02")
    assert plan is not None and plan["id"] == "wp-2026-11-02"


def test_a_corrupted_read_back_leaves_an_unverified_row_and_the_rerun_sends_only_that_routine() -> (
    None
):
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()

    with pytest.raises(Invalid) as failed:
        push(conn, hevy, data, digest)
    after_failure = len(hevy.audit)
    left = routine_map.every(conn)
    rerun = push(conn, hevy, data, digest)
    after_rerun = len(hevy.audit)
    settled = push(conn, hevy, data, digest)

    assert failed.value.code == "verify_failed"
    assert [(session, status) for session, _, status in left] == [("lower", "unverified")]
    assert [(o.session_id, o.action, o.outcome) for o in rerun.routines] == [
        ("lower", "update", "verified"),
        ("upper", "create", "verified"),
    ]
    assert after_rerun - after_failure == 2 * 2 + 2
    assert rerun.resumed
    assert [o.outcome for o in settled.routines] == ["unchanged", "unchanged"]
    assert len(hevy.audit) == after_rerun
    assert {status for _, _, status in routine_map.every(conn)} == {"active"}


def test_a_superseding_plan_flips_the_earlier_row_and_inherits_no_acknowledgement() -> None:
    conn = a_squat_week()
    hevy = pushed(conn)
    data = a_plan_draft(conn, hevy=True, overrides=PIN_115)

    dry = dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )
    result = approved(conn, data, hevy)

    assert dry.checked.draft.supersedes == "wp-2026-11-02"
    assert result.week_plan_id == "wp-2026-11-02-2"
    rows = {r["id"]: r for r in week_plans.every_of_week(conn, "2026-11-02")}
    assert (rows["wp-2026-11-02"]["status"], rows["wp-2026-11-02"]["superseded_by"]) == (
        "superseded",
        "wp-2026-11-02-2",
    )
    assert rows["wp-2026-11-02-2"]["status"] == "approved"
    assert [(o.action, o.outcome) for o in result.routines] == [("update", "verified")]


def test_without_hevy_the_plan_is_approved_and_nothing_is_sent() -> None:
    conn = a_squat_week()
    data = a_plan_draft(conn)

    result = push(conn, None, data, the_hash(conn, data, hevy=False))

    plan = week_plans.in_force(conn, "2026-11-02")
    assert plan is not None and plan["id"] == result.week_plan_id
    assert result.routines == ()
    [row] = week_plans.prescriptions(conn, result.week_plan_id)
    assert row["change"] == "4×6–8 @8: 120 → 125"
    assert cast(list[object], row["steps"])[0] == {
        "step": "scheme",
        "from": 120.0,
        "to": 125.0,
        "cause": "hit",
    }


def adopted(conn: Connection, *sessions: dict[str, object]) -> None:
    adopt(
        conn,
        toml(a_draft(*sessions)),
        file="next.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def test_a_retired_sessions_routine_becomes_a_spare_the_next_new_session_takes_before_a_post() -> (
    None
):
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    approved(conn, a_plan_draft(conn, hevy=True), hevy)
    upper = routine_map.mapped(conn)["upper"]
    adopted(conn, a_session("lower", a_line("bb_back_squat")))
    hevy.calls.clear()

    approved(conn, a_plan_draft(conn, hevy=True), hevy)
    retired_folder = next(f.hevy_id for f in mirrors.folders(conn) if f.role == "retired")
    spare = hevy.routine(upper)
    retire_puts = [c for c in hevy.calls if c == ("PUT", f"/v1/routines/{upper}")]
    adopted(conn, a_session("lower", a_line("bb_back_squat")), a_session("pull"))
    hevy.calls.clear()
    taken = approved(conn, a_plan_draft(conn, hevy=True), hevy)

    assert len(retire_puts) == 1
    assert (spare.title, spare.folder_id) == ("(unused) Upper", retired_folder)
    assert len(spare.exercises) == 1
    assert ("POST", "/v1/routines") not in hevy.calls
    assert [(o.session_id, o.routine_id, o.action) for o in taken.routines][-1] == (
        "pull",
        upper,
        "create",
    )
    assert routine_map.mapped(conn)["pull"] == upper


def test_a_template_is_created_and_recorded_on_the_exercise_before_the_routine_is_written() -> None:
    conn = a_squat_week()
    columns = {
        "hevy_title": "Back Squat (home)",
        "hevy_exercise_type": "weight_reps",
        "hevy_equipment": "barbell",
        "hevy_muscle_group": "quadriceps",
    }
    with conn:
        exercises.update(conn, "bb_back_squat", {"hevy_template_id": None, **columns})
    hevy = FakeHevy(FixedClock())

    approved(conn, a_plan_draft(conn, hevy=True), hevy)

    squat = exercises.get(conn, "bb_back_squat")
    assert squat is not None
    template = str(squat["hevy_template_id"])
    assert requests(hevy)[:2] == [
        ("POST", "/v1/routine_folders"),
        ("POST", "/v1/exercise_templates"),
    ]
    routine = hevy.routine(lower_routine(conn))
    assert routine.exercises[0].hevy_template_id == template


def a_folder_payload(id_: int, title: str) -> dict[str, object]:
    return {"id": id_, "index": 0, "title": title, "updated_at": None, "created_at": None}


def test_a_folder_with_the_engine_title_is_adopted_and_two_of_them_refuse_the_push() -> None:
    conn = a_squat_week()
    data = a_plan_draft(conn, hevy=True)
    one = FakeHevy(FixedClock(), folders=[a_folder_payload(7, "Program")])
    two = FakeHevy(
        FixedClock(), folders=[a_folder_payload(7, "Program"), a_folder_payload(8, "Program")]
    )

    with pytest.raises(Refused) as shared:
        approved(conn, data, two)
    approved(conn, data, one)

    assert shared.value.code == "folder_title_shared"
    assert [c for c in two.calls if c[0] != "GET"] == []
    assert ("POST", "/v1/routine_folders") not in one.calls
    assert hevy_folder(one, lower_routine(conn)) == "7"


def hevy_folder(hevy: FakeHevy, routine_id: str) -> str | None:
    return hevy.routine(routine_id).folder_id


def test_the_plan_freezes_its_overrides_acknowledgements_and_each_lines_flags() -> None:
    conn = a_squat_week()
    squat_logged(conn, "h-2", "2026-10-28", *[(121, 8, 8)] * 4)
    offgrid = "offgrid_anchor_ignored@line:2026-11-02/lower/bb_back_squat"
    raised = dry_run(
        conn,
        a_plan_draft(conn),
        file="p.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(),
    )
    params_hash = next(f.params_hash for f in raised.flags if f.key == offgrid)
    acknowledge = (
        f'[[acknowledge]]\nflag = "{offgrid}"\nparams_hash = "{params_hash}"\n'
        'because = "kit"\ntext = "A mislabelled plate."\n'
    )
    data = a_plan_draft(conn, overrides=PIN_115, acknowledge=acknowledge)

    result = push(conn, None, data, the_hash(conn, data, hevy=False))

    [override] = week_plans.overrides(conn, result.week_plan_id)
    assert (override["kind"], override["params"]) == ("pin_load", {"load": 115})
    [row] = week_plans.prescriptions(conn, result.week_plan_id)
    [flag] = cast(list[dict[str, Any]], row["flags"])
    assert (flag["key"], flag["left"]["because"]) == (offgrid, "kit")
    assert week_plans.acknowledgements(conn, result.week_plan_id) == [(offgrid, params_hash, "kit")]


def test_status_shows_the_plan_in_force_with_its_routines_verified_and_unverified() -> None:
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    push(conn, hevy, data, digest)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        approved(conn, a_plan_draft(conn, hevy=True, overrides=PIN_115), hevy)

    shown = status(
        conn,
        FixedClock(datetime.datetime(2026, 11, 3, 9, 0, tzinfo=datetime.UTC)),
        engine_version="0.3.0",
        pin="0.3.0",
        hevy_on=True,
        exported={},
    ).plan

    assert shown is not None
    assert (shown.id, shown.week, shown.routines_verified, shown.routines_unverified) == (
        "wp-2026-11-02-2",
        "2026-11-02",
        1,
        ("lower",),
    )
