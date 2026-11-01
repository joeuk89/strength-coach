import importlib.metadata
import sqlite3
from pathlib import Path

import pytest
from support.cli import run_coach
from support.instances import an_instance

from coach.cli import app

DEV_ENGINE = "0.3.0.dev0"
RELEASE_ENGINE = "0.3.0"


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setattr(app, "engine_version", lambda: RELEASE_ENGINE)
    return monkeypatch


def test_status_outside_an_instance_stops_with_no_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["ok"] is False
    assert run.envelope["verb"] == "status"
    assert run.envelope["error"]["code"] == "no_instance"
    assert run.stdout.count("\n") == 1


def test_status_with_a_matching_pin_reports_engine_and_schema_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(an_instance(tmp_path, pin=RELEASE_ENGINE))

    run = run_coach("status")

    assert run.code == 0
    assert run.envelope == {
        "schema_version": 1,
        "ok": True,
        "verb": "status",
        "result": {
            "engine": {"version": RELEASE_ENGINE, "pin": RELEASE_ENGINE},
            "schema_version": 1,
        },
        "warnings": [],
    }


def test_status_finds_the_instance_from_a_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance(tmp_path / "athlete", pin=RELEASE_ENGINE)
    nested = root / "pages" / "routines"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    run = run_coach("status")

    assert run.code == 0
    assert (root / ".coach" / "coach.db").exists()


def test_a_dev_engine_against_a_release_pin_runs_with_engine_pin_dev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: DEV_ENGINE)
    monkeypatch.chdir(an_instance(tmp_path, pin="0.2.0"))

    run = run_coach("status")

    assert run.code == 0
    assert [w["code"] for w in run.envelope["warnings"]] == ["engine_pin_dev"]
    assert run.envelope["result"]["engine"] == {"version": DEV_ENGINE, "pin": "0.2.0"}


def test_the_engine_version_is_the_installed_package_version() -> None:
    assert app.engine_version() == importlib.metadata.version("coach")


def test_a_release_engine_against_a_different_pin_stops_with_engine_pin_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance(tmp_path, pin="0.2.0")
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "engine_pin_mismatch"
    assert not (root / ".coach").exists()


def test_a_store_behind_the_engine_stops_with_schema_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance(tmp_path, pin=RELEASE_ENGINE)
    (root / ".coach").mkdir()
    old = sqlite3.connect(root / ".coach" / "coach.db")
    old.execute("CREATE TABLE session (id TEXT PRIMARY KEY)")
    old.commit()
    old.close()
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "schema_behind"


def test_an_unreadable_coach_toml_stops_with_a_setup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "coach.toml").write_text("[engine\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "config_unknown_key"


def test_a_coach_toml_without_an_engine_pin_stops_with_engine_pin_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "coach.toml").write_text("[athlete]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "engine_pin_mismatch"
