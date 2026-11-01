from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.instances import an_instance

from coach.cli import app

ENGINE = "0.3.0"
FILE = """date = 2026-10-30
tier = "deep"
read = "state carried from the old instance"
window_start = 2026-10-26

[[observation]]
text = "drift adds volume"
"""


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE)
    monkeypatch.chdir(root)
    return root


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=FixedClock())


def test_checkin_record_returns_the_row_its_window_and_the_ids_by_kind(instance: Path) -> None:
    (instance / "ci.toml").write_text(FILE, encoding="utf-8")

    run = coach("checkin", "record", "ci.toml")

    assert run.code == 0
    result = run.envelope["result"]
    assert result["check_in"] == "ci-2026-10-30"
    assert result["tier"] == "deep"
    assert result["window"] == {"start": "2026-10-26", "end": "2026-10-30"}
    assert result["ids"] == {"observation": ["o-0001"]}
    assert result["superseded"] is None


def test_a_second_file_setting_window_start_is_exit_1(instance: Path) -> None:
    (instance / "a.toml").write_text(FILE, encoding="utf-8")
    (instance / "b.toml").write_text(FILE.replace("2026-10-30", "2026-11-06"), encoding="utf-8")
    coach("checkin", "record", "a.toml")

    run = coach("checkin", "record", "b.toml")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
