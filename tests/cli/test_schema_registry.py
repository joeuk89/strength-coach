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


def test_the_flags_registry_shows_each_code_with_severity_scope_and_rn() -> None:
    run = run_coach("schema", "--registry", "flags", "--full")

    rows = {row["code"]: row for row in run.envelope["result"]["rows"]}
    assert run.envelope["result"]["truncated"] is False
    assert len(rows) == run.envelope["result"]["count"] == 83
    assert rows["stall_streak"]["severity"] == "warning"
    assert rows["stall_streak"]["scope"] == ["line"]
    assert rows["stall_streak"]["rn"] == "rn:progression-methods §4"
    assert rows["load_off_grid"]["severity"] == "violation"
    assert rows["load_off_grid"]["rn"] is None
    assert rows["light_week_unprompted"]["rn"] == ["rn:deloads.3", "rn:deloads.4"]
    assert rows["recovery_ceiling_exceeded"]["rn"]["cases"]["niggle"] is None
    assert rows["override_conflict"]["scope"] == ["week", "session", "line"]


def test_the_default_flags_envelope_truncates_under_3_kb() -> None:
    run = run_coach("schema", "--registry", "flags")

    result = run.envelope["result"]
    assert len(run.stdout.encode("utf-8")) < 3 * 1024
    assert result["truncated"] is True
    assert len(result["rows"]) == 10
    assert result["count"] == 83


def test_last_keeps_that_many_rows() -> None:
    run = run_coach("schema", "--registry", "flags", "--last", "3")

    assert [row["code"] for row in run.envelope["result"]["rows"]] == [
        "load_off_grid",
        "recovery_ceiling_exceeded",
        "return_band_disagrees",
    ]
