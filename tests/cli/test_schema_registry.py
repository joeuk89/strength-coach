from pathlib import Path

import pytest
from support.cli import run_coach


@pytest.fixture(autouse=True)
def outside_an_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_a_registry_prints_as_rows() -> None:
    run = run_coach("schema", "--registry", "reasons")

    assert run.code == 0
    result = run.envelope["result"]
    assert result["registry"] == "reasons"
    assert [row["name"] for row in result["rows"]] == [
        "pain",
        "kit",
        "stall",
        "fatigue",
        "schedule",
        "athlete_request",
        "coach_judgement",
    ]
    assert result["count"] == 7
    assert result["truncated"] is False


def test_an_unknown_registry_is_exit_1() -> None:
    run = run_coach("schema", "--registry", "colours")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


def test_a_verb_and_a_registry_together_are_invalid() -> None:
    run = run_coach("schema", "status", "--registry", "reasons")

    assert run.code == 1
