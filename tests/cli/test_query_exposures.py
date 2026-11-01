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


def test_the_last_five_bench_exposures_come_newest_first_marked_truncated(instance: Path) -> None:
    run = coach("query", "exposures", "--exercise", "bb_bench_press", "--last", "5")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert [row["date"] for row in result["rows"]] == [
        "2026-10-26",
        "2026-10-19",
        "2026-10-12",
        "2026-10-05",
        "2026-09-28",
    ]
    assert {row["exposure"].split("/")[1] for row in result["rows"]} == {"bb_bench_press"}
    assert result["rows"][0]["load"] == 117.5
    assert (result["count"], result["truncated"]) == (8, True)


def test_exercise_repeats_and_since_bounds_the_dates(instance: Path) -> None:
    run = coach(
        "query",
        "exposures",
        "--exercise",
        "bb_bench_press",
        "--exercise",
        "bb_back_squat",
        "--since",
        "2026-10-26",
    )

    assert [row["exposure"] for row in run.envelope["result"]["rows"]] == [
        "exposure:h-7/bb_back_squat",
        "exposure:h-7/bb_bench_press",
    ]


def test_a_since_that_is_not_a_date_is_exit_1(instance: Path) -> None:
    run = coach("query", "exposures", "--since", "last week")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
