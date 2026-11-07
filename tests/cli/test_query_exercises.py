from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.history import an_instance_with_eight_weeks

from coach.cli import app

ENGINE = "0.3.0"


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance_with_eight_weeks(tmp_path, pin=ENGINE)
    monkeypatch.chdir(root)
    return root


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=FixedClock())


def test_the_library_reads_by_id_with_each_exercise_s_fields(instance: Path) -> None:
    run = coach("query", "exercises")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert [row["id"] for row in result["rows"]] == ["bb_back_squat", "bb_bench_press"]
    assert result["rows"][1] == {
        "id": "bb_bench_press",
        "name": "bb bench press",
        "load_mode": "total",
        "equipment_kind": "barbell",
        "pattern": "horizontal_push",
        "muscles": {"primary": ["chest"], "secondary": []},
        "hevy_template_id": "79D0BB3A",
        "source": "catalogue",
    }
    assert (result["count"], result["truncated"]) == (2, False)


def test_match_pattern_and_muscle_narrow_the_library_together(instance: Path) -> None:
    run = coach(
        "query",
        "exercises",
        "--match",
        "BENCH",
        "--pattern",
        "squat",
        "--pattern",
        "horizontal_push",
        "--muscle",
        "chest",
    )

    assert [row["id"] for row in run.envelope["result"]["rows"]] == ["bb_bench_press"]


def test_the_last_n_exercises_say_more_exist(instance: Path) -> None:
    result = coach("query", "exercises", "--last", "1").envelope["result"]

    assert [row["id"] for row in result["rows"]] == ["bb_back_squat"]
    assert (result["count"], result["truncated"]) == (2, True)


def test_schema_declares_the_exercises_filters_and_the_registry_lists_the_view() -> None:
    declared = run_coach("schema", "query").envelope["result"]["input"]["properties"]
    views = run_coach("schema", "--registry", "views", "--full").envelope["result"]["rows"]

    assert declared["match"]["type"] == "string"
    assert declared["pattern"]["type"] == "array"
    assert declared["muscle"]["type"] == "array"
    assert {"name": "exercises", "params": ["--match", "--pattern", "--muscle", "--last"]} in views
