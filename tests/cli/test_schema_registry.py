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


def test_the_flags_registry_names_what_may_leave_each_code() -> None:
    run = run_coach("schema", "--registry", "flags", "--full")

    rows = {row["code"]: row for row in run.envelope["result"]["rows"]}
    assert rows["stall_streak"]["left_by"] == ["weekplan", "decision"]
    assert rows["cadence_slow"]["left_by"] == ["decision"]
    assert rows["cadence_fast"]["left_by"] == ["decision"]
    assert rows["routine_drift"]["left_by"] == []
    assert rows["load_off_grid"]["left_by"] == []
    assert "acknowledgeable" not in rows["stall_streak"]


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


def test_the_phase_registry_gives_kinds_default_rates_and_trend_bands() -> None:
    run = run_coach("schema", "--registry", "phase")

    rows = {row["name"]: row for row in run.envelope["result"]["rows"]}
    assert rows["deficit"]["default_rate_pct_bw_per_week"] == -0.5
    assert rows["surplus"]["default_rate_pct_bw_per_week"] == 0.25
    assert rows["maintenance"]["trend_band"] == {"half_width": 0.25, "unit": "pct_bw_per_week"}
    assert rows["deficit"]["trend_band"] == {"half_width": 50, "unit": "pct_of_rate"}
    assert rows["surplus"]["rn"] == "rn:training-level §4"


def test_the_schemes_registry_names_the_one_scheme_that_reads_a_training_max() -> None:
    run = run_coach("schema", "--registry", "schemes")

    rows = run.envelope["result"]["rows"]
    assert [row["name"] for row in rows if row["reads_training_max"]] == ["wave_531"]


def test_the_record_kinds_registry_reserves_the_observation_to_the_check_in() -> None:
    run = run_coach("schema", "--registry", "record-kinds", "--full")

    rows = run.envelope["result"]["rows"]
    assert len(rows) == 12
    assert [row["name"] for row in rows if row["check_in_only"]] == ["observation"]


def test_the_follow_up_record_kind_is_spelled_as_its_table() -> None:
    run = run_coach("schema", "--registry", "record-kinds")

    rows = run.envelope["result"]["rows"]
    assert {"name": "follow_up", "table": "[[follow_up]]", "check_in_only": False} in rows
