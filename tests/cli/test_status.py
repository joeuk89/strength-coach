import hashlib
import importlib.metadata
import shutil
import sqlite3
from pathlib import Path

import pytest
from support.cli import run_coach
from support.instances import an_instance
from support.kit_fixtures import INVENTORY, TABLES

from coach.cli import app
from coach.store.chain import ENGINE as CHAIN

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


def test_status_with_a_matching_pin_reports_engine_and_store_schema_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(an_instance(tmp_path, pin=RELEASE_ENGINE))

    run = run_coach("status")

    assert run.code == 0
    assert run.envelope == {
        "schema_version": CHAIN.version,
        "ok": True,
        "verb": "status",
        "result": {
            "engine": {"version": RELEASE_ENGINE, "pin": RELEASE_ENGINE},
            "hevy": {"on": False, "last_import": None, "last_import_age_days": None},
            "workouts": {"hevy": 0, "manual": 0},
            "store_schema_version": CHAIN.version,
            "kit": [],
            "export": {"behind_store": True, "store_behind_export": False},
            "plan": None,
            "rotation": None,
            "program": None,
            "goal": None,
            "phase": None,
            "check_in": {
                "due": False,
                "due_on": None,
                "tier": "light",
                "catch_up": False,
                "window": None,
            },
            "niggles": {"count": 0, "ids": []},
            "follow_ups_due": {"count": 0, "ids": []},
            "decisions": {},
            "observations": {"count": 0, "ids": []},
            "block": None,
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
    [warning] = run.envelope["warnings"]
    assert warning["params_hash"].startswith("sha256:")
    assert warning == {
        "key": "engine_pin_dev@instance",
        "code": "engine_pin_dev",
        "severity": "warning",
        "scope": {"kind": "instance"},
        "params": {"pinned_version": "0.2.0", "running_version": DEV_ENGINE},
        "params_hash": warning["params_hash"],
        "rn": None,
        "message": f"engine {DEV_ENGINE} is a development build running against pin 0.2.0",
        "left": None,
    }
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


def test_status_reports_hevy_on_when_coach_toml_has_the_hevy_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(an_instance(tmp_path, pin=RELEASE_ENGINE, hevy=True))

    run = run_coach("status")

    assert run.code == 0
    assert run.envelope["result"]["hevy"]["on"] is True


def test_an_unknown_key_in_coach_toml_stops_status_with_config_unknown_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance(tmp_path, pin=RELEASE_ENGINE, caps={"squat": 100})
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "config_unknown_key"
    assert "caps" in run.envelope["error"]["message"]
    assert not (root / ".coach").exists()


def test_an_implements_value_naming_no_implement_stops_status_with_config_unknown_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    gym = {
        "kind": "grid",
        "implements": {"barbell": "trap_bar"},
        "implement": {"bar": {"increment": 2.5}},
    }
    monkeypatch.chdir(an_instance(tmp_path, pin=RELEASE_ENGINE, location={"gym": gym}))

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "config_unknown_key"
    assert "location.gym.implements.barbell" in run.envelope["error"]["message"]


def test_an_unknown_timezone_stops_status_with_config_unknown_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance(tmp_path, pin=RELEASE_ENGINE)
    text = (root / "coach.toml").read_text(encoding="utf-8")
    (root / "coach.toml").write_text(text.replace("Europe/London", "Mars/Olympus"))
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "config_unknown_key"
    assert "athlete.timezone" in run.envelope["error"]["message"]


HOME = {
    "kind": "plate-pool",
    "kit": "home",
    "implements": {"barbell": "barbell"},
    "implement": {"barbell": {"hardware": "collar-clamp"}},
}


def an_instance_with_the_fixture_kit(root: Path) -> Path:
    an_instance(root, pin=RELEASE_ENGINE, location={"home": HOME})
    (root / "kit").mkdir()
    shutil.copyfile(INVENTORY, root / "kit" / "home.json")
    shutil.copyfile(TABLES, root / "kit" / "home.achievable.json")
    return root


def test_status_reports_kit_tables_built_from_the_inventory_as_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(an_instance_with_the_fixture_kit(tmp_path))

    run = run_coach("status")

    assert run.code == 0
    assert run.envelope["result"]["kit"] == [
        {"location": "home", "kit": "home", "tables": "current"}
    ]


def test_status_reports_kit_tables_stale_once_the_inventory_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance_with_the_fixture_kit(tmp_path)
    inventory = root / "kit" / "home.json"
    inventory.write_bytes(inventory.read_bytes().replace(b'"count": 4', b'"count": 6', 1))
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.code == 0
    assert run.envelope["result"]["kit"] == [{"location": "home", "kit": "home", "tables": "stale"}]


def test_status_reports_a_missing_tables_file_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance_with_the_fixture_kit(tmp_path)
    (root / "kit" / "home.achievable.json").unlink()
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.envelope["result"]["kit"] == [{"location": "home", "kit": "home", "tables": "stale"}]


def test_status_lists_no_kit_tables_for_a_grid_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    gym = {
        "kind": "grid",
        "implements": {"barbell": "bar"},
        "implement": {"bar": {"increment": 2.5}},
    }
    monkeypatch.chdir(an_instance(tmp_path, pin=RELEASE_ENGINE, location={"gym": gym}))

    run = run_coach("status")

    assert run.envelope["result"]["kit"] == []


def test_status_keeps_no_kit_hash_in_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance_with_the_fixture_kit(tmp_path)
    monkeypatch.chdir(root)

    run_coach("status")

    store = sqlite3.connect(root / ".coach" / "coach.db")
    dump = "\n".join(store.iterdump())
    store.close()
    assert hashlib.sha256(INVENTORY.read_bytes()).hexdigest()[:8] not in dump
    assert "sha256" not in dump


def test_a_hand_edit_to_a_generated_file_warns_generated_file_drift_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: pytest.MonkeyPatch
) -> None:
    root = an_instance(tmp_path, pin=RELEASE_ENGINE)
    with (root / "CLAUDE.md").open("a", encoding="utf-8") as claude_md:
        claude_md.write("Always answer in French.\n")
    (root / ".claude" / "settings.json").unlink()
    monkeypatch.chdir(root)

    run = run_coach("status")

    assert run.code == 0
    drift = [w for w in run.envelope["warnings"] if w["code"] == "generated_file_drift"]
    assert [(w["key"], w["severity"], w["scope"], w["rn"], w["left"]) for w in drift] == [
        ("generated_file_drift@instance", "warning", {"kind": "instance"}, None, None)
    ] * 2
    assert [w["params"] for w in drift] == [
        {"file": ".claude/settings.json", "engine_version": RELEASE_ENGINE},
        {"file": "CLAUDE.md", "engine_version": RELEASE_ENGINE},
    ]
    assert all(w["params_hash"].startswith("sha256:") for w in drift)
    assert drift[0]["message"].startswith(".claude/settings.json ")
    assert drift[1]["message"].startswith("CLAUDE.md ")
