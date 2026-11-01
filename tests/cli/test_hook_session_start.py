import json
from pathlib import Path

import pytest
from support.hook import run_hook
from support.instances import an_instance

from coach.cli import app
from coach.cli.hook.in_process import run_in_process


@pytest.fixture(autouse=True)
def release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: "0.3.0")


def a_session(cwd: Path) -> str:
    return json.dumps({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(cwd)})


def test_session_start_in_an_instance_gives_coach_status_as_context(tmp_path: Path) -> None:
    an_instance(tmp_path, pin="0.3.0")

    run = run_hook("session-start", a_session(tmp_path), run_coach=run_in_process)

    assert run.code == 0
    output = run.answer["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    status = json.loads(output["additionalContext"])
    assert status["verb"] == "status"
    assert status["result"]["engine"] == {"version": "0.3.0", "pin": "0.3.0"}


def test_session_start_inside_an_instance_subdirectory_finds_the_instance(tmp_path: Path) -> None:
    an_instance(tmp_path, pin="0.3.0")
    (tmp_path / "pages").mkdir()

    run = run_hook("session-start", a_session(tmp_path / "pages"), run_coach=run_in_process)

    assert json.loads(run.answer["hookSpecificOutput"]["additionalContext"])["ok"] is True


def test_session_start_with_a_pin_mismatch_shows_the_refusal(tmp_path: Path) -> None:
    an_instance(tmp_path, pin="0.2.0")

    run = run_hook("session-start", a_session(tmp_path), run_coach=run_in_process)

    status = json.loads(run.answer["hookSpecificOutput"]["additionalContext"])
    assert status["error"]["code"] == "engine_pin_mismatch"


def test_session_start_outside_an_instance_says_nothing(tmp_path: Path) -> None:
    run = run_hook("session-start", a_session(tmp_path), run_coach=run_in_process)

    assert run.code == 0
    assert run.stdout == ""


def test_an_unknown_event_is_an_error_that_blocks_nothing() -> None:
    run = run_hook("post-tool-use", "{}")

    assert run.code == 1
    assert run.stdout == ""
