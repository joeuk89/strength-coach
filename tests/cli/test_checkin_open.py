from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.instances import an_instance

from coach.cli import app

ENGINE = "0.3.0"
NIGGLE = """
[[niggle]]
site = "left knee"
opened = 2026-10-20
date = 2026-10-20
status = "reported"
"""


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE)
    monkeypatch.chdir(root)
    return root


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=FixedClock())


def test_checkin_open_returns_the_card_and_its_warnings(instance: Path) -> None:
    (instance / "n.toml").write_text(NIGGLE, encoding="utf-8")
    coach("record", "n.toml")

    run = coach("checkin", "open", "--date", "2026-10-30")

    assert run.code == 0
    result = run.envelope["result"]
    assert (result["tier"], result["window"]) == (
        "light",
        {"start": "2026-10-30", "end": "2026-10-30"},
    )
    assert [f["field"] for f in result["card"]] == [
        "header",
        "readiness",
        "sleep",
        "weight_phase",
        "niggles",
    ]
    assert result["card"][-1]["asks"] == [{"ask": "niggle_status", "about": "niggle:n-0001"}]
    assert [w["code"] for w in run.envelope["warnings"]] == ["niggle_unconstrained"]


def test_tier_deep_raises_the_tier(instance: Path) -> None:
    run = coach("checkin", "open", "--tier", "deep")

    assert run.envelope["result"]["tier"] == "deep"


def test_a_tier_other_than_light_or_deep_is_exit_1(instance: Path) -> None:
    run = coach("checkin", "open", "--tier", "heavy")

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
