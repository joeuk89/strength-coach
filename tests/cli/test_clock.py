import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.instances import an_instance

from coach.cli import app, registry
from coach.cli.clock import clock_for, machine_timezone
from coach.cli.declaration import Call, Declaration, Outcome
from coach.core.clock import Clock

MONDAY = datetime.datetime(2026, 11, 2, 9, 0, tzinfo=ZoneInfo("Europe/London"))


def a_verb_reporting_today(seen: list[Clock]) -> Declaration:
    def run(call: Call) -> Outcome:
        assert call.clock is not None
        seen.append(call.clock)
        return Outcome({"today": call.clock.today().isoformat()})

    return Declaration(
        name="today", summary="Today.", writes="none", needs_instance=True, output={}, run=run
    )


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: "0.3.0")
    root = an_instance(tmp_path, pin="0.3.0")
    monkeypatch.chdir(root)
    return root


def test_a_fixed_clock_handed_to_main_is_the_clock_every_verb_receives(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Clock] = []
    monkeypatch.setattr(registry, "declarations", lambda: (a_verb_reporting_today(seen),))
    fixed = FixedClock(MONDAY)

    first = run_coach("today", clock=fixed)
    second = run_coach("today", clock=fixed)

    assert seen == [fixed, fixed]
    assert first.envelope["result"] == second.envelope["result"] == {"today": "2026-11-02"}


def test_without_a_clock_main_builds_one_in_the_athletes_timezone(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Clock] = []
    monkeypatch.setattr(registry, "declarations", lambda: (a_verb_reporting_today(seen),))

    run = run_coach("today")

    assert run.code == 0
    (clock,) = seen
    assert clock.now().utcoffset() == datetime.datetime.now(ZoneInfo("Europe/London")).utcoffset()


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
def test_the_system_clock_reads_today_in_its_timezone(zone: str) -> None:
    clock = clock_for(zone)

    now = clock.now()

    assert now.tzinfo == ZoneInfo(zone)
    assert clock.today() == datetime.datetime.now(ZoneInfo(zone)).date()


def test_the_machine_timezone_comes_from_tz_when_it_names_a_zone() -> None:
    assert machine_timezone({"TZ": "Asia/Tokyo"}) == "Asia/Tokyo"


def test_the_machine_timezone_is_a_zone_name_without_tz() -> None:
    assert ZoneInfo(machine_timezone({"TZ": "not a zone"}))
