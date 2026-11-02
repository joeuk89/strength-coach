from pathlib import Path

import pytest
from support.blocks import BOUNDARY, WHY, two_closed_blocks
from support.cli import Run, run_coach
from support.clock import FixedClock, at
from support.instances import an_instance

from coach.cli import app
from coach.cli.envelope import BUDGET_BYTES
from coach.store.connection import connect

ENGINE = "0.3.0"


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An instance whose store holds two closed Blocks of bench and pull-ups."""
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE)
    (root / ".coach").mkdir()
    built = two_closed_blocks(bench_tops=(100, 105, 105, 110, 115, 115), thursday_pull_ups=True)
    on_disk = connect(root / ".coach" / "coach.db")
    built.backup(on_disk)
    on_disk.close()
    monkeypatch.chdir(root)
    return root


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=FixedClock(at(BOUNDARY)))


def test_progress_reports_the_closed_block_under_the_budget(instance: Path) -> None:
    run = coach("progress")

    assert run.code == 0
    result = run.envelope["result"]
    assert result["block"]["id"] == "b-2026-11-23"
    bench = result["priority_lifts"][0]
    assert bench["exercise"] == "bb_bench_press"
    assert [b["block"] for b in bench["e1rm_by_block"]] == ["b-2026-10-30", "b-2026-11-23"]
    assert result["goal"]["why"] == WHY
    assert [w["code"] for w in run.envelope["warnings"]] == ["cadence_slow"]
    assert len(run.stdout.encode("utf-8")) < BUDGET_BYTES


def test_full_adds_per_line_history(instance: Path) -> None:
    compact = coach("progress").envelope["result"]
    full = coach("progress", "--full").envelope["result"]

    assert "history" not in compact
    assert [h["exercise"] for h in full["history"]] == ["bb_bench_press", "pull_up"]
    assert len(full["history"][0]["exposures"]) == 3
