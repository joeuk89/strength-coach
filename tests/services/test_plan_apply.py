import datetime
from collections import Counter
from dataclasses import replace
from typing import Any, cast

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.kit_fixtures import kit_files
from support.plan_drafts import a_plan_draft
from support.plans import SQUAT_TEMPLATE, a_squat_program, squat_logged
from support.program_drafts import a_draft, a_line, a_session, toml
from support.programs import a_config

from coach.core.errors import Invalid, Refused
from coach.services.plan_apply import ApplyResult, DryRun, apply, dry_run
from coach.services.program import adopt
from coach.services.record import record
from coach.services.status import status
from coach.store import exercises, mirrors, routine_map, week_plans
from coach.store.connection import Connection

BENCH_TEMPLATE = "BP-0001"


def a_squat_week(*sessions: dict[str, object], **draft: object) -> Connection:
    conn = a_squat_program(*sessions, **draft)
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
    clock: FixedClock | None = None,
) -> ApplyResult:
    return apply(
        conn,
        hevy,
        data,
        file="plan.toml",
        expect=expect,
        config=a_config(hevy=hevy is not None),
        kits=(kit_files(),),
        clock=clock or FixedClock(),
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


def test_a_routine_moved_in_hevy_refuses_the_push_before_any_put_and_approves_the_plan() -> None:
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
    assert plan is not None and plan["id"] == "wp-2026-11-02-2"


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

    assert dry.summary.supersedes == "wp-2026-11-02"
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
        units="lb",
    ).plan

    assert shown is not None
    assert (shown.id, shown.week, shown.routines_verified, shown.routines_unverified) == (
        "wp-2026-11-02-2",
        "2026-11-02",
        0,
        ("lower", "upper"),
    )


def test_a_session_in_force_but_unplanned_this_week_keeps_its_routine_verified() -> None:
    conn = a_squat_week(
        a_session("lower", a_line("bb_back_squat")),
        a_session("upper"),
        schedule={
            "rotation": ["A", "B"],
            "A": {"mon": "lower", "wed": "upper"},
            "B": {"mon": "lower"},
        },
    )
    hevy = FakeHevy(FixedClock())
    approved(conn, a_plan_draft(conn, hevy=True), hevy)
    approved(conn, a_plan_draft(conn, hevy=True, week=datetime.date(2026, 11, 9)), hevy)

    shown = status(
        conn,
        FixedClock(datetime.datetime(2026, 11, 10, 9, 0, tzinfo=datetime.UTC)),
        engine_version="0.3.0",
        pin="0.3.0",
        hevy_on=True,
        exported={},
        units="lb",
    ).plan

    assert shown is not None
    assert (shown.week, shown.routines_verified, shown.routines_unverified) == (
        "2026-11-09",
        2,
        (),
    )


SWAP = """
[[override]]
kind = "swap_exercise"
session = "lower"
exercise = "bb_back_squat"
to = "goblet_squat"
start_load = 50
because = "pain"
text = "The knee settles under a goblet."
"""


def persisting(conn: Connection, week: datetime.date) -> list[str]:
    data = a_plan_draft(conn, overrides=SWAP, week=week)
    found = dry_run(
        conn, data, file="p.toml", config=a_config(), kits=(kit_files(),), clock=FixedClock()
    )
    push(conn, None, data, found.write_plan_hash)
    return [f.key for f in found.flags if f.code == "override_persisting"]


def test_the_third_consecutive_plan_with_the_same_swap_raises_override_persisting() -> None:
    conn = a_squat_week()

    first = persisting(conn, datetime.date(2026, 11, 2))
    second = persisting(conn, datetime.date(2026, 11, 9))
    third = persisting(conn, datetime.date(2026, 11, 16))

    assert (first, second) == ([], [])
    assert third == ["override_persisting@line:2026-11-16/lower/bb_back_squat"]


def test_after_a_failed_verify_the_rerun_sends_only_the_unverified_routine() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, data, digest)
    sent = len(requests(hevy))

    push(conn, hevy, data, digest)

    assert requests(hevy)[sent:] == [("PUT", f"/v1/routines/{lower_routine(conn)}")]


def a_rerun_dry_run(conn: Connection, data: bytes) -> DryRun:
    return dry_run(
        conn,
        data,
        file="plan.toml",
        config=a_config(hevy=True),
        kits=(kit_files(),),
        clock=FixedClock(),
    )


def test_the_dry_run_after_a_failed_verify_resumes_the_plan_and_does_not_supersede_it() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, data, digest)

    found = a_rerun_dry_run(conn, data)

    assert (found.resumes, found.summary.supersedes) == ("wp-2026-11-02", None)


def test_resuming_a_superseding_plan_keeps_the_plan_it_superseded() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    approved(conn, a_plan_draft(conn, hevy=True), hevy)
    superseding = a_plan_draft(conn, hevy=True, overrides=PIN_115)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        approved(conn, superseding, hevy)

    found = a_rerun_dry_run(conn, superseding)

    assert (found.resumes, found.summary.supersedes) == (
        "wp-2026-11-02-2",
        "wp-2026-11-02",
    )


def test_a_superseding_plan_freezes_only_its_own_acknowledgements() -> None:
    conn = a_squat_week()
    squat_logged(conn, "h-2", "2026-10-28", *[(121, 8, 8)] * 4)
    offgrid = "offgrid_anchor_ignored@line:2026-11-02/lower/bb_back_squat"
    first = a_plan_draft(conn)
    params_hash = next(
        f.params_hash
        for f in dry_run(
            conn, first, file="p.toml", config=a_config(), kits=(kit_files(),), clock=FixedClock()
        ).flags
        if f.key == offgrid
    )
    acknowledge = (
        f'[[acknowledge]]\nflag = "{offgrid}"\nparams_hash = "{params_hash}"\n'
        'because = "kit"\ntext = "A mislabelled plate."\n'
    )
    acknowledged = a_plan_draft(conn, acknowledge=acknowledge)
    earlier = push(conn, None, acknowledged, the_hash(conn, acknowledged, hevy=False))
    superseding = a_plan_draft(conn, overrides=PIN_115)

    later = push(conn, None, superseding, the_hash(conn, superseding, hevy=False))

    assert len(week_plans.acknowledgements(conn, earlier.week_plan_id)) == 1
    assert week_plans.acknowledgements(conn, later.week_plan_id) == []
    [row] = week_plans.prescriptions(conn, later.week_plan_id)
    assert [f["left"] for f in cast(list[dict[str, Any]], row["flags"])] == [None]


def moved_in_hevy_and_imported(conn: Connection, hevy: FakeHevy, routine_id: str) -> None:
    """The athlete edits the routine in the app after approval, then an import mirrors it."""
    moved_at = "2026-10-31T09:00:00Z"
    hevy.move_routine(routine_id, moved_at)
    [stored] = [r for r in mirrors.routines(conn) if r.hevy_id == routine_id]
    with conn:
        mirrors.upsert_routine(conn, replace(stored, updated_at=moved_at), "2026-10-31T10:00:00Z")


def test_a_routine_changed_in_the_mirror_after_approval_gives_the_resume_a_new_hash() -> None:
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, data, digest)
    moved_in_hevy_and_imported(conn, hevy, lower_routine(conn))
    sent = len(requests(hevy))

    found = a_rerun_dry_run(conn, data)
    with pytest.raises(Refused) as stale:
        push(conn, hevy, data, digest)
    refused_sent = len(requests(hevy))
    resumed = push(conn, hevy, data, found.write_plan_hash)

    assert found.write_plan_hash != digest
    assert found.moved_routines == (lower_routine(conn),)
    assert stale.value.code == "expect_mismatch"
    assert refused_sent == sent
    assert resumed.resumed
    assert [(o.session_id, o.outcome) for o in resumed.routines] == [
        ("lower", "verified"),
        ("upper", "verified"),
    ]


def test_resumes_after_approval_keep_the_approved_hash_while_only_the_push_wrote_the_routines() -> (
    None
):
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, data, digest)
    next_day = FixedClock(datetime.datetime(2026, 10, 31, 12, 0, tzinfo=datetime.UTC))
    resumed = push(conn, hevy, data, digest, next_day)

    found = a_rerun_dry_run(conn, data)
    settled = push(conn, hevy, data, digest, next_day)

    assert [o.outcome for o in resumed.routines] == ["verified", "verified"]
    assert (found.write_plan_hash, found.moved_routines) == (digest, ())
    assert settled.resumed
    assert [o.outcome for o in settled.routines] == ["unchanged", "unchanged"]


def test_a_settled_rerun_on_a_later_day_keeps_the_approved_hash_for_the_next_resume() -> None:
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, data, digest)
    push(
        conn,
        hevy,
        data,
        digest,
        FixedClock(datetime.datetime(2026, 10, 31, 12, tzinfo=datetime.UTC)),
    )
    settled = push(
        conn,
        hevy,
        data,
        digest,
        FixedClock(datetime.datetime(2026, 11, 1, 12, tzinfo=datetime.UTC)),
    )

    found = a_rerun_dry_run(conn, data)
    again = push(
        conn,
        hevy,
        data,
        digest,
        FixedClock(datetime.datetime(2026, 11, 2, 12, tzinfo=datetime.UTC)),
    )

    assert [o.outcome for o in settled.routines] == ["unchanged", "unchanged"]
    assert (found.write_plan_hash, found.moved_routines) == (digest, ())
    assert again.resumed
    assert [o.outcome for o in again.routines] == ["unchanged", "unchanged"]


def a_failed_push(conn: Connection, hevy: FakeHevy, data: bytes) -> str:
    """The Draft approved and its push failed on the first read-back; returns the hash."""
    digest = the_hash(conn, data)
    hevy.differ_next_read_back()
    with pytest.raises(Invalid):
        push(conn, hevy, data, digest)
    return digest


def test_a_resumed_dry_run_shows_the_frozen_prescriptions_after_an_import_moved_the_anchor() -> (
    None
):
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = a_failed_push(conn, hevy, data)
    squat_logged(conn, "h-2", "2026-10-30", *[(140, 8, 8)] * 4)

    found = a_rerun_dry_run(conn, data)

    shown = [
        (session.session_id, line.exercise_id, line.change)
        for session in found.summary.sessions
        for line in session.lines
    ]
    assert shown == [("lower", "bb_back_squat", "4×6–8 @8: 120 → 125")]
    [frozen] = week_plans.prescriptions(conn, "wp-2026-11-02")
    assert [line.set_groups for s in found.summary.sessions for line in s.lines] == [
        frozen["set_groups"]
    ]
    assert found.write_plan_hash == digest


def test_a_resume_works_out_its_hevy_actions_from_the_frozen_week_plan() -> None:
    conn = a_squat_week(a_session("lower", a_line("bb_back_squat")), a_session("upper"))
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = a_failed_push(conn, hevy, data)
    adopt(
        conn,
        toml(a_draft(a_session("lower", a_line("bb_back_squat")))),
        file="next.toml",
        config=a_config(),
        kits=(kit_files(),),
        clock=FixedClock(datetime.datetime(2026, 10, 31, 12, tzinfo=datetime.UTC)),
    )

    found = a_rerun_dry_run(conn, data)
    resumed = push(conn, hevy, data, digest)

    assert found.actions.to_json()["routines"] == {
        "update": [{"session": "lower", "routine": lower_routine(conn)}],
        "create": [{"session": "upper", "routine": None}],
        "retire": [],
    }
    assert [(o.session_id, o.action, o.outcome) for o in resumed.routines] == [
        ("lower", "update", "verified"),
        ("upper", "create", "verified"),
    ]


AGGRAVATED_KNEE = """
[[niggle]]
site = "left knee"
date = 2026-10-30
status = "aggravated"

[[niggle.constraints]]
kind = "load_cap"
exercise = "bb_back_squat"
value = 100
"""


def test_a_flag_that_became_a_violation_after_approval_does_not_block_the_resume() -> None:
    conn = a_squat_week()
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True, overrides=PIN_115)
    digest = a_failed_push(conn, hevy, data)
    record(conn, AGGRAVATED_KNEE.encode(), file="knee.toml", clock=FixedClock())

    resumed = push(conn, hevy, data, digest)

    assert resumed.resumed
    assert [(o.session_id, o.outcome) for o in resumed.routines] == [("lower", "verified")]


def bench_before_squat() -> Connection:
    return a_squat_week(a_session("lower", a_line("bb_bench_press"), a_line("bb_back_squat")))


def test_a_resumed_dry_run_lists_a_sessions_lines_in_the_order_the_athlete_approved() -> None:
    conn = bench_before_squat()
    data = a_plan_draft(conn, hevy=True)

    fresh = a_rerun_dry_run(conn, data)
    push(conn, FakeHevy(FixedClock()), data, fresh.write_plan_hash)
    resumed = a_rerun_dry_run(conn, data)

    assert resumed.resumes == "wp-2026-11-02"
    for found in (fresh, resumed):
        assert [(s.session_id, s.date.isoformat()) for s in found.summary.sessions] == [
            ("lower", "2026-11-02")
        ]
        assert [line.exercise_id for line in found.summary.sessions[0].lines] == [
            "bb_bench_press",
            "bb_back_squat",
        ]


def test_the_routine_follows_the_authored_order_and_a_resume_keeps_the_approved_hash() -> None:
    conn = bench_before_squat()
    hevy = FakeHevy(FixedClock())
    data = a_plan_draft(conn, hevy=True)
    digest = the_hash(conn, data)

    push(conn, hevy, data, digest)

    routine = hevy.routine(lower_routine(conn))
    assert [e.hevy_template_id for e in routine.exercises] == [BENCH_TEMPLATE, SQUAT_TEMPLATE]
    assert a_rerun_dry_run(conn, data).write_plan_hash == digest
