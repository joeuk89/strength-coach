"""`progress` and `publish` take the zone from the clock: a rung recorded at 23:30 UTC on Monday
starts on Tuesday in Tokyo, so Monday's exposure counts toward it only in UTC."""

import datetime
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.git import isolate_git
from support.ladders import a_ladder_program, ladder_rung_decision, logged

from coach.cli import app
from coach.services.record import record
from coach.store.connection import connect

ENGINE = "0.3.0"
TOKYO = ZoneInfo("Asia/Tokyo")
LATE_MONDAY = datetime.datetime(2026, 11, 2, 23, 30, tzinfo=datetime.UTC)


def on_sunday(zone: datetime.tzinfo) -> FixedClock:
    return FixedClock(datetime.datetime(2026, 11, 8, 12, tzinfo=zone))


@pytest.fixture(scope="module")
def initialised(tmp_path_factory: pytest.TempPathFactory) -> Path:
    home = tmp_path_factory.mktemp("home")
    root = home / "athlete"
    root.mkdir()
    with pytest.MonkeyPatch.context() as patch:
        isolate_git(patch, home)
        patch.setattr(app, "engine_version", lambda: ENGINE)
        patch.chdir(root)
        assert run_coach("init", "--defaults").code == 0
    built = a_ladder_program()
    record(built, ladder_rung_decision(2).encode(), file="d.toml", clock=FixedClock(LATE_MONDAY))
    logged(built, "ab_wheel", "2026-11-02", 8)
    on_disk = connect(root / ".coach" / "coach.db")
    built.backup(on_disk)
    on_disk.close()
    return root


@pytest.fixture
def instance(initialised: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    isolate_git(monkeypatch, tmp_path)
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = tmp_path / "athlete"
    shutil.copytree(initialised, root)
    monkeypatch.chdir(root)
    return root


@pytest.mark.parametrize(("zone", "exposures"), [(datetime.UTC, 1), (TOKYO, 0)])
def test_progress_dates_the_rung_in_the_clocks_zone(
    instance: Path, zone: datetime.tzinfo, exposures: int
) -> None:
    run = run_coach("progress", clock=on_sunday(zone))

    assert run.code == 0, run.stdout
    [row] = run.envelope["result"]["ladders"]
    assert row["exposures"] == exposures


@pytest.mark.parametrize(("zone", "exposures"), [(datetime.UTC, 1), (TOKYO, 0)])
def test_publish_dates_the_rung_in_the_clocks_zone(
    instance: Path, zone: datetime.tzinfo, exposures: int
) -> None:
    run = run_coach("publish", clock=on_sunday(zone))

    assert run.code == 0, run.stdout
    page = (instance / "pages" / "progress.md").read_text(encoding="utf-8")
    assert f"| lower/dead_bug | 2 of 3, ab_wheel | {exposures} of 2 | no |" in page
