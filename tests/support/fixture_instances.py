"""pytest fixtures over the Fixture instance: one copy per module with its store rebuilt, and a
copy of that per test."""

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

from coach.cli import app
from coach.cli.declaration import MakeClient
from coach.core.clock import Clock
from support.cli import Run, run_coach
from support.clock import FixedClock, at
from support.fake_hevy import FakeHevy
from support.fixture_instance import KEY, PIN, TODAY, a_fixture_instance, hevy_holding

CLOCK = FixedClock(at(TODAY))


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path]:
    root = a_fixture_instance(tmp_path_factory.mktemp("fixture") / "athlete")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(app, "engine_version", lambda: PIN)
        patch.chdir(root)
        assert run_coach("status", clock=CLOCK).code == 0
    yield root


@pytest.fixture
def instance(rebuilt: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "athlete"
    shutil.copytree(rebuilt, root)
    monkeypatch.setattr(app, "engine_version", lambda: PIN)
    monkeypatch.chdir(root)
    return root


def serving(hevy: FakeHevy) -> MakeClient:
    def make_client(key: str, audit_path: Path, clock: Clock) -> FakeHevy:
        return hevy

    return make_client


def coach(*argv: str, hevy: FakeHevy | None = None, env: dict[str, str] | None = None) -> Run:
    """Run `coach` in the current instance with Hevy holding what its mirror says, or `hevy`."""
    held = hevy or hevy_holding(Path.cwd(), CLOCK)
    return run_coach(*argv, env=KEY if env is None else env, clock=CLOCK, make_client=serving(held))
