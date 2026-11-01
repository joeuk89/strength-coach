from pathlib import Path

import pytest
from support.hook import a_bash_call, run_hook
from support.instances import an_instance

from coach.cli import app
from coach.cli.hook.in_process import run_in_process
from coach.cli.registry import declarations


@pytest.fixture(autouse=True)
def release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: "0.3.0")


def test_init_asks_with_the_tree_its_own_dry_run_would_write(tmp_path: Path) -> None:
    run = run_hook(
        "pre-tool-use",
        a_bash_call("coach init --defaults", cwd=str(tmp_path)),
        declarations=declarations(),
        run_coach=run_in_process,
    )

    assert run.decision == "ask"
    assert '"coach.toml"' in run.reason
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_init_inside_an_instance_is_denied_with_the_refusal(tmp_path: Path) -> None:
    an_instance(tmp_path, pin="0.3.0")

    run = run_hook(
        "pre-tool-use",
        a_bash_call("coach init --defaults", cwd=str(tmp_path)),
        declarations=declarations(),
        run_coach=run_in_process,
    )

    assert run.decision == "deny"
    assert "instance_exists" in run.reason


def test_the_dry_run_leaves_the_working_directory_where_it_was(tmp_path: Path) -> None:
    before = Path.cwd()

    run_in_process(["init", "--defaults", "--dry-run"], tmp_path)

    assert Path.cwd() == before
