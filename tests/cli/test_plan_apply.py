from pathlib import Path

import pytest
from support.hook import a_bash_call, run_hook
from support.planning_instance import (
    ENGINE,
    a_planning_instance,
    adopt_the_squat_version,
    coach,
    the_store,
)
from support.plans import squat_logged

from coach.cli import app
from coach.cli.hook.in_process import run_in_process
from coach.cli.registry import declarations

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


def test_without_dry_run_the_push_is_refused_in_this_build(instance: Path) -> None:
    run = coach("plan", "apply", a_draft_file(instance), "--expect", "sha256:x")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


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
