from pathlib import Path

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.hevy_payloads import a_workout, an_exercise
from support.instances import an_instance

from coach.cli import app
from coach.cli.declaration import MakeClient
from coach.core.clock import Clock

ENGINE = "0.3.0"
KEY = {"HEVY_API_KEY": "a-key"}
A = "10000000-0000-4000-8000-00000000000a"


def serving(fake: FakeHevy) -> MakeClient:
    def make_client(key: str, audit_path: Path, clock: Clock) -> FakeHevy:
        return fake

    return make_client


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE, hevy=True)
    monkeypatch.chdir(root)
    return root


def test_without_a_hevy_table_import_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    monkeypatch.chdir(an_instance(tmp_path, pin=ENGINE))

    run = run_coach("import", env=KEY)

    assert run.code == 0
    assert run.envelope["result"] == {"skipped": True, "rebuilt": None}


def test_a_hevy_table_with_no_key_is_hevy_key_missing(instance: Path) -> None:
    run = run_coach("import", clock=FixedClock(), make_client=serving(FakeHevy(FixedClock())))

    assert run.code == 5
    assert run.envelope["error"]["code"] == "hevy_key_missing"


def test_an_unreachable_hevy_is_exit_4(instance: Path) -> None:
    fake = FakeHevy(FixedClock())
    fake.fail_next_get()

    run = run_coach("import", env=KEY, clock=FixedClock(), make_client=serving(fake))

    assert run.code == 4
    assert run.envelope["error"]["code"] == "hevy_unreachable"


def test_a_full_import_reports_its_counts_and_warnings_as_flags(instance: Path) -> None:
    clock = FixedClock()
    custom = a_workout(A, exercises=[an_exercise("C0FFEE01", "Hollow Hold")])
    built: list[tuple[str, Path]] = []

    def make_client(key: str, audit_path: Path, _clock: Clock) -> FakeHevy:
        built.append((key, audit_path))
        return FakeHevy(clock, workouts=[custom])

    run = run_coach("import", "--full", env=KEY, clock=clock, make_client=make_client)

    assert run.code == 0
    assert built == [("a-key", instance / "hevy" / "writes.jsonl")]
    assert run.envelope["result"] == {
        "rebuilt": None,
        "kind": "full",
        "window": {"since": None, "until": "2026-10-30T12:00:00Z"},
        "workouts": {"new": 1, "versioned": 0, "gone": 0, "back": 0},
        "weigh_ins": 0,
        "routines": 0,
        "folders": 0,
    }
    (warning,) = run.envelope["warnings"]
    assert warning["key"] == f"exercise_unmapped@workout:{A}"
    assert warning["severity"] == "warning"
    assert warning["params"] == {"hevy_template_id": "C0FFEE01", "title": "Hollow Hold"}

    status = run_coach("status", env=KEY, clock=clock)
    assert status.envelope["result"]["hevy"] == {
        "on": True,
        "last_import": "2026-10-30T12:00:00Z",
        "last_import_age_days": 0,
    }
    assert status.envelope["result"]["workouts"] == {"hevy": 1, "manual": 0}
