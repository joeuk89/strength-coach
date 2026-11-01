from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.fake_hevy import FakeHevy
from support.hook import a_bash_call, run_hook
from support.planning_instance import (
    CLOCK,
    ENGINE,
    a_planning_instance,
    adopt_the_squat_version,
    coach,
    the_store,
)
from support.plans import squat_logged
from support.worked_week import a_dry_run, the_worked_week

from coach.cli import app, envelope
from coach.cli.hook.in_process import run_in_process
from coach.cli.registry import declarations
from coach.cli.verbs.plan_apply import dry_run_result
from coach.core.clock import Clock
from coach.store import mirrors

PIN_OFF_RACK = """
[[override]]
kind = "pin_load"
session = "lower"
exercise = "bb_back_squat"
load = 115
because = "coach_judgement"
text = "Hold the squat under the last top set."
"""
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


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = a_planning_instance(tmp_path / "athlete")
    monkeypatch.chdir(root)
    adopt_the_squat_version(root)
    conn = the_store(root)
    squat_logged(conn, "h-1", "2026-10-26", *[(121, 8, 8)] * 4)
    conn.close()
    return root


def a_draft_file(root: Path, *, overrides: str = "") -> str:
    drafted = coach("plan", "draft", "--week", "2026-11-02").envelope["result"]
    path = root / drafted["path"]
    text = path.read_text().replace("confirmed = false", "confirmed = true")
    if overrides:
        text = text.replace("override = []\n", "", 1) + overrides
    (root / "plan.toml").write_text(text)
    return "plan.toml"


def test_a_clean_dry_run_is_exit_0_with_the_summary_the_hash_and_the_prompt(
    instance: Path,
) -> None:
    run = coach("plan", "apply", a_draft_file(instance), "--dry-run")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["week"] == "2026-11-02"
    assert result["position"] == {"week": "A", "source": "program_adopt"}
    assert result["write_plan_hash"].startswith("sha256:")
    assert result["folders_to_create"] == []
    assert result["routines"] == {"update": [], "create": [], "retire": []}
    assert result["templates_to_create"] == []
    assert [(f["key"], f["severity"], f["left"]) for f in result["flags"]] == [
        ("offgrid_anchor_ignored@line:2026-11-02/lower/bb_back_squat", "warning", None)
    ]
    assert result["prompt"].splitlines()[-1] == f"Write plan hash {result['write_plan_hash']}"
    assert "Hevy actions: none" in result["prompt"]


def test_a_violation_is_exit_1_with_every_flag_of_the_plan(instance: Path) -> None:
    (instance / "knee.toml").write_text(KNEE_CAP)
    assert coach("record", "knee.toml").code == 0

    run = coach("plan", "apply", a_draft_file(instance, overrides=PIN_OFF_RACK), "--dry-run")

    assert run.code == 1
    error = run.envelope["error"]
    assert error["code"] == "recovery_ceiling_exceeded"
    assert [f["severity"] for f in error["flags"]] == ["violation", "warning"]


def test_the_dry_run_writes_nothing(instance: Path) -> None:
    draft = a_draft_file(instance)
    before = sorted(p.relative_to(instance) for p in instance.rglob("*"))
    store = (instance / ".coach" / "coach.db").read_bytes()

    coach("plan", "apply", draft, "--dry-run")

    assert sorted(p.relative_to(instance) for p in instance.rglob("*")) == before
    assert (instance / ".coach" / "coach.db").read_bytes() == store


def test_without_expect_the_push_is_exit_3_expect_missing(instance: Path) -> None:
    run = coach("plan", "apply", a_draft_file(instance))

    assert run.code == 3
    assert run.envelope["error"]["code"] == "expect_missing"


def hevy_on(hevy: FakeHevy) -> Callable[..., Run]:
    def serving(key: str, audit_path: Path, clock: Clock) -> FakeHevy:
        return hevy

    def with_hevy(*argv: str) -> Run:
        return run_coach(*argv, env={"HEVY_API_KEY": "k"}, clock=CLOCK, make_client=serving)

    return with_hevy


def test_a_read_back_that_differs_is_exit_1_verify_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = a_planning_instance(tmp_path / "athlete", hevy=True)
    monkeypatch.chdir(root)
    adopt_the_squat_version(root)
    hevy = FakeHevy(CLOCK)
    with_hevy = hevy_on(hevy)
    draft = a_draft_file(root)
    digest = with_hevy("plan", "apply", draft, "--dry-run").envelope["result"]["write_plan_hash"]
    hevy.differ_next_read_back()

    run = with_hevy("plan", "apply", draft, "--expect", digest)

    assert run.code == 1
    assert run.envelope["error"]["code"] == "verify_failed"
    routines = coach("query", "routines").envelope["result"]["rows"]
    assert [r["status"] for r in routines] == ["unverified"]


def test_the_dry_run_after_a_failed_verify_prompts_to_resume_the_approved_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = a_planning_instance(tmp_path / "athlete", hevy=True)
    monkeypatch.chdir(root)
    adopt_the_squat_version(root)
    hevy = FakeHevy(CLOCK)
    with_hevy = hevy_on(hevy)
    draft = a_draft_file(root)
    digest = with_hevy("plan", "apply", draft, "--dry-run").envelope["result"]["write_plan_hash"]
    hevy.differ_next_read_back()
    with_hevy("plan", "apply", draft, "--expect", digest)

    result = with_hevy("plan", "apply", draft, "--dry-run").envelope["result"]

    assert (result["resumes"], result["supersedes"]) == ("wp-2026-11-02", None)
    assert result["prompt"].splitlines()[0] == (
        "Plan 2026-11-02 to 2026-11-08, rotation week A, resuming wp-2026-11-02"
    )


def test_a_resume_after_a_routine_moved_refuses_the_old_hash_and_pushes_under_the_new_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = a_planning_instance(tmp_path / "athlete", hevy=True)
    monkeypatch.chdir(root)
    adopt_the_squat_version(root)
    hevy = FakeHevy(CLOCK)
    with_hevy = hevy_on(hevy)
    draft = a_draft_file(root)
    digest = with_hevy("plan", "apply", draft, "--dry-run").envelope["result"]["write_plan_hash"]
    hevy.differ_next_read_back()
    with_hevy("plan", "apply", draft, "--expect", digest)
    [routine] = [r["routine"] for r in coach("query", "routines").envelope["result"]["rows"]]
    hevy.move_routine(routine, "2026-10-31T09:00:00Z")
    conn = the_store(root)
    [stored] = [r for r in mirrors.routines(conn) if r.hevy_id == routine]
    with conn:
        mirrors.upsert_routine(
            conn, replace(stored, updated_at="2026-10-31T09:00:00Z"), "2026-10-31T10:00:00Z"
        )
    conn.close()

    dry = with_hevy("plan", "apply", draft, "--dry-run").envelope["result"]
    stale = with_hevy("plan", "apply", draft, "--expect", digest)
    fresh = with_hevy("plan", "apply", draft, "--expect", dry["write_plan_hash"])

    assert dry["write_plan_hash"] != digest
    assert dry["moved_routines"] == [routine]
    assert f"Changed in Hevy since approval: {routine}" in dry["prompt"].splitlines()
    assert (stale.code, stale.envelope["error"]["code"]) == (3, "expect_mismatch")
    assert fresh.code == 0, fresh.stdout
    assert fresh.envelope["result"]["resumed"] is True


def test_the_approved_hash_pushes_the_plan_to_hevy_and_a_rerun_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = a_planning_instance(tmp_path / "athlete", hevy=True)
    monkeypatch.chdir(root)
    adopt_the_squat_version(root)
    hevy = FakeHevy(CLOCK)

    with_hevy = hevy_on(hevy)
    draft = a_draft_file(root)
    digest = with_hevy("plan", "apply", draft, "--dry-run").envelope["result"]["write_plan_hash"]
    first = with_hevy("plan", "apply", draft, "--expect", digest)
    again = with_hevy("plan", "apply", draft, "--expect", digest)

    assert first.code == 0, first.stdout
    result = first.envelope["result"]
    assert (result["week_plan_id"], result["write_plan_hash"]) == ("wp-2026-11-02", digest)
    [outcome] = result["outcomes"]
    assert (outcome["session"], outcome["action"], outcome["outcome"]) == (
        "lower",
        "create",
        "verified",
    )
    assert result["audit_lines"] == 5
    assert (result["outcome_count"], result["outcomes_truncated"]) == (1, False)
    assert again.code == 0, again.stdout
    assert again.envelope["result"]["resumed"] is True
    assert [o["outcome"] for o in again.envelope["result"]["outcomes"]] == ["unchanged"]
    routines = coach("query", "routines").envelope["result"]["rows"]
    assert [(r["session"], r["folder"], r["status"]) for r in routines] == [
        ("lower", "Program", "active")
    ]


def test_query_flags_on_a_draft_summarises_by_code_and_severity(instance: Path) -> None:
    draft = a_draft_file(instance)
    text = (instance / draft).read_text().replace("confirmed = true", "confirmed = false")
    (instance / draft).write_text(text)

    run = coach("query", "flags", "--draft", draft, "--summary")

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["rows"] == [
        {"code": "offgrid_anchor_ignored", "severity": "warning", "count": 1},
        {"code": "rotation_unconfirmed", "severity": "violation", "count": 1},
    ]


def test_query_flags_filters_a_draft_by_severity(instance: Path) -> None:
    run = coach("query", "flags", "--draft", a_draft_file(instance), "--severity", "warning")

    assert [r["key"] for r in run.envelope["result"]["rows"]] == [
        "offgrid_anchor_ignored@line:2026-11-02/lower/bb_back_squat"
    ]


def test_query_lines_on_a_draft_lists_each_line_with_its_change(instance: Path) -> None:
    run = coach("query", "lines", "--draft", a_draft_file(instance), "--changed")

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["rows"] == [
        {
            "date": "2026-11-02",
            "session": "lower",
            "exercise": "bb_back_squat",
            "prescription": "4×6–8 at 125 lb",
            "change": "4×6–8 @8: 120 → 125",
            "flags": ["offgrid_anchor_ignored@line:2026-11-02/lower/bb_back_squat"],
        }
    ]


def test_query_flags_and_lines_with_no_plan_in_force_return_no_rows(instance: Path) -> None:
    for view in ("flags", "lines"):
        run = coach("query", view)

        assert run.code == 0, run.stdout
        assert run.envelope["result"] == {"rows": [], "count": 0, "truncated": False}


def test_full_carries_each_flag_whole(instance: Path) -> None:
    run = coach("plan", "apply", a_draft_file(instance), "--dry-run", "--full")

    [flag] = run.envelope["result"]["flags"]
    assert flag["params"] == {
        "exposure": "exposure:h-1/bb_back_squat",
        "logged_load": 121.0,
        "anchor_used": 120.0,
    }


def test_the_hook_asks_with_the_prompt_of_the_real_dry_run(instance: Path) -> None:
    draft = a_draft_file(instance)
    digest = coach("plan", "apply", draft, "--dry-run").envelope["result"]["write_plan_hash"]

    run = run_hook(
        "pre-tool-use",
        a_bash_call(f"coach plan apply {draft} --expect {digest}", cwd=str(instance)),
        declarations=declarations(),
        run_coach=run_in_process,
    )

    assert run.decision == "ask"
    assert f"Write plan hash {digest}" in run.reason


def test_the_default_dry_run_of_the_worked_week_fits_the_envelope_budget() -> None:
    found = a_dry_run(the_worked_week())
    result = dry_run_result(found, units="lb", full=False, last=10)

    document = envelope.render(envelope.success(1, "plan apply", result, []), pretty=False)

    assert len(document.encode("utf-8")) < 3 * 1024
    assert result["flag_count"] == len(found.flags) == 4
    assert result["flags"] == [
        {"key": flag.key, "severity": "warning", "left": None} for flag in found.flags
    ]
