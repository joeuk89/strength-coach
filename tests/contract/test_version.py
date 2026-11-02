import json
from importlib.metadata import version
from pathlib import Path

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.fixture_instances import serving


@pytest.fixture(autouse=True)
def outside_an_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("argv", [("--version",), ("status", "--version")])
def test_version_outside_an_instance_is_one_envelope_naming_the_installed_version(
    argv: tuple[str, ...],
) -> None:
    run = run_coach(*argv, make_client=serving(FakeHevy(FixedClock())))

    assert run.code == 0
    document = json.loads(run.stdout)
    assert document["ok"] is True
    assert document["verb"] is None
    assert document["result"] == {"version": version("coach")}
    assert document["warnings"] == []
    assert run.stdout.count("\n") == 1


def test_version_takes_no_value() -> None:
    run = run_coach("--version=1", make_client=serving(FakeHevy(FixedClock())))

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
