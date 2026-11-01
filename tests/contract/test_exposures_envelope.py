from pathlib import Path

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.history import an_instance_with_eight_weeks

from coach.cli import app

ENGINE = "0.3.0"


def test_query_exposures_last_five_is_under_3_kb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    monkeypatch.chdir(an_instance_with_eight_weeks(tmp_path, pin=ENGINE))

    run = run_coach(
        "query", "exposures", "--exercise", "bb_bench_press", "--last", "5", clock=FixedClock()
    )

    assert run.code == 0
    assert run.envelope["result"]["truncated"] is True
    assert len(run.stdout.encode("utf-8")) < 3 * 1024
