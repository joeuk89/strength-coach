import json
import shutil
import sqlite3
import tomllib
from pathlib import Path

import pytest
from support.chains import ENGINE_PLUS_PROBE
from support.cli import run_coach
from support.git import commit_everything, commit_subjects, committed_files, isolate_git

from coach.cli import app
from coach.cli.generated import generated_files
from coach.store import chain

PINNED = "0.3.0"
NEWER = "0.4.0"

EDITED_EXERCISE = """
[[exercise]]
id = "ab_wheel"
name = "Ab Wheel Rollout"
load_mode = "bodyweight"
equipment_kind = "bodyweight"
pattern = "core"
muscles = {primary = ["abdominals"], secondary = []}
hevy_template_id = "A1B2C3D4-0000"
hevy_title = "Ab Wheel"
"""


@pytest.fixture(scope="module")
def initialised(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One instance `init` made at engine 0.3.0, copied into each test: init and git are slow."""
    home = tmp_path_factory.mktemp("initialised")
    root = home / "athlete"
    root.mkdir()
    with pytest.MonkeyPatch.context() as monkeypatch:
        isolate_git(monkeypatch, home)
        monkeypatch.chdir(root)
        running(monkeypatch, PINNED)
        assert run_coach("init", "--defaults").code == 0
    return root


@pytest.fixture
def instance(initialised: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """That instance, committed, with the engine now at 0.4.0."""
    isolate_git(monkeypatch, tmp_path)
    root = tmp_path / "athlete"
    shutil.copytree(initialised, root)
    monkeypatch.chdir(root)
    running(monkeypatch, NEWER)
    return root


def running(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: version)


def with_a_newer_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chain, "ENGINE", ENGINE_PLUS_PROBE)


def pin(root: Path) -> str:
    return tomllib.loads((root / "coach.toml").read_text())["engine"]["version"]


def store_version(root: Path) -> int:
    conn = sqlite3.connect(root / ".coach" / "coach.db")
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    conn.close()
    return version


def files_of(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_upgrade_from_an_older_pin_migrates_exports_regenerates_bumps_and_commits_once(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_a_newer_schema(monkeypatch)

    run = run_coach("upgrade")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["from"] == PINNED
    assert result["to"] == NEWER
    assert result["migrations"] == ["m0001"]
    assert result["schema_version"] == {"from": 1, "to": 2}
    assert {"CLAUDE.md", "coach.toml"} <= set(result["files"])
    assert "export/upgrade_probe.jsonl" in result["files"]
    assert commit_subjects(instance) == [f"coach upgrade v{NEWER}", f"coach init v{PINNED}"]
    assert result["commit"] is not None
    assert pin(instance) == NEWER
    assert store_version(instance) == 2
    assert f"coach engine {NEWER}" in (instance / "CLAUDE.md").read_text()
    for relative, text in generated_files(NEWER).items():
        assert (instance / relative).read_text() == text
    manifest = json.loads((instance / "export" / "manifest.json").read_text())
    assert manifest["schema_version"] == 2
    assert manifest["engine_version"] == NEWER
    assert {"export/manifest.json", "export/upgrade_probe.jsonl"} <= committed_files(instance)
    assert run_coach("status").envelope["warnings"] == []


def test_upgrade_run_again_is_a_no_op(instance: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with_a_newer_schema(monkeypatch)
    run_coach("upgrade")
    before = files_of(instance)

    again = run_coach("upgrade")

    assert again.code == 0, again.stdout
    assert again.envelope["result"]["commit"] is None
    assert again.envelope["result"]["migrations"] == []
    assert again.envelope["result"]["files"] == []
    assert len(commit_subjects(instance)) == 2
    assert files_of(instance) == before


def test_a_second_machine_with_the_pin_current_and_its_store_behind_migrates_without_a_commit(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_a_newer_schema(monkeypatch)
    database = instance / ".coach" / "coach.db"
    behind = database.read_bytes()
    assert run_coach("upgrade").code == 0
    database.write_bytes(behind)
    before = files_of(instance)
    subjects = commit_subjects(instance)

    run = run_coach("upgrade")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["migrations"] == ["m0001"]
    assert result["commit"] is None
    assert store_version(instance) == 2
    assert commit_subjects(instance) == subjects
    assert {k: v for k, v in files_of(instance).items() if not k.startswith(".coach/")} == {
        k: v for k, v in before.items() if not k.startswith(".coach/")
    }


def test_a_dry_run_lists_the_migrations_and_files_and_changes_nothing(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_a_newer_schema(monkeypatch)
    before = files_of(instance)

    run = run_coach("upgrade", "--dry-run")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["dry_run"] is True
    assert result["migrations"] == ["m0001"]
    assert {"CLAUDE.md", "coach.toml", "export/upgrade_probe.jsonl"} <= set(result["files"])
    assert "commit" not in result
    assert files_of(instance) == before
    assert len(commit_subjects(instance)) == 1


def test_hand_edits_to_the_generated_files_warn_on_status_until_upgrade_rewrites_them(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(monkeypatch, PINNED)
    generated = (instance / "CLAUDE.md").read_text()
    (instance / "CLAUDE.md").write_text(generated + "Always answer in French.\n")
    (instance / ".claude" / "settings.json").write_text('{"permissions": {}}\n')
    commit_everything(instance, "athlete edits the generated files")

    drift = run_coach("status").envelope["warnings"]
    run = run_coach("upgrade")

    assert [w["code"] for w in drift] == ["generated_file_drift"] * 2
    assert drift[1]["message"].startswith("CLAUDE.md ")
    assert run.code == 0, run.stdout
    assert run.envelope["result"]["files"][:2] == [".claude/settings.json", "CLAUDE.md"]
    for relative, text in generated_files(PINNED).items():
        assert (instance / relative).read_text() == text
    assert commit_subjects(instance)[0] == f"coach upgrade v{PINNED}"
    assert run_coach("status").envelope["warnings"] == []


def test_a_dirty_tree_refuses_with_git_tree_dirty_and_changes_nothing(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_a_newer_schema(monkeypatch)
    (instance / "profile.md").write_text("# Athlete\n")
    before = files_of(instance)

    run = run_coach("upgrade")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "git_tree_dirty"
    assert "profile.md" in run.envelope["error"]["message"]
    assert files_of(instance) == before
    assert len(commit_subjects(instance)) == 1


def test_an_engine_older_than_the_pin_refuses_with_engine_pin_mismatch_and_changes_nothing(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(monkeypatch, "0.2.9")
    before = files_of(instance)

    run = run_coach("upgrade")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "engine_pin_mismatch"
    assert files_of(instance) == before
    assert len(commit_subjects(instance)) == 1


@pytest.mark.parametrize(
    "argv",
    [("status",), ("query", "readings", "--kind", "weigh_in")],
    ids=["status", "query"],
)
def test_no_ordinary_verb_migrates_a_store_behind_the_engine(
    instance: Path, monkeypatch: pytest.MonkeyPatch, argv: tuple[str, ...]
) -> None:
    running(monkeypatch, PINNED)
    with_a_newer_schema(monkeypatch)

    behind = run_coach(*argv)
    upgraded = run_coach("upgrade")
    after = run_coach(*argv)

    assert behind.code == 5
    assert behind.envelope["error"]["code"] == "schema_behind"
    assert upgraded.code == 0, upgraded.stdout
    assert after.code == 0, after.stdout
    assert store_version(instance) == 2


def test_upgrade_leaves_an_edited_catalogue_row_exactly_as_it_was(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(monkeypatch, PINNED)
    draft = instance / "edit.toml"
    draft.write_text(EDITED_EXERCISE)
    assert run_coach("record", str(draft)).code == 0
    draft.unlink()
    database = instance / ".coach" / "coach.db"
    conn = sqlite3.connect(database)
    edited = conn.execute("SELECT * FROM exercise WHERE id = 'ab_wheel'").fetchone()
    conn.close()
    running(monkeypatch, NEWER)

    run = run_coach("upgrade")

    assert run.code == 0, run.stdout
    conn = sqlite3.connect(database)
    assert conn.execute("SELECT * FROM exercise WHERE id = 'ab_wheel'").fetchone() == edited
    conn.close()
    assert edited[10] == "A1B2C3D4-0000"


def test_a_dev_engine_refuses_to_upgrade_and_leaves_engine_pin_dev_standing(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(monkeypatch, "0.4.0.dev0")

    status = run_coach("status")
    run = run_coach("upgrade")

    assert [w["code"] for w in status.envelope["warnings"]] == ["engine_pin_dev"]
    assert run.code == 5
    assert run.envelope["error"]["code"] == "engine_pin_required"
    assert pin(instance) == PINNED


def test_upgrade_on_a_release_build_clears_engine_pin_dev(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(monkeypatch, "0.4.0.dev0")
    on_dev = run_coach("status").envelope["warnings"]
    running(monkeypatch, NEWER)

    run = run_coach("upgrade")

    assert [w["code"] for w in on_dev] == ["engine_pin_dev"]
    assert run.code == 0, run.stdout
    assert run_coach("status").envelope["warnings"] == []


def test_an_export_ahead_of_the_store_refuses_with_store_behind_export_and_changes_nothing(
    instance: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(monkeypatch, PINNED)
    assert run_coach("publish").code == 0
    running(monkeypatch, NEWER)
    with_a_newer_schema(monkeypatch)
    manifest_path = instance / "export" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tables"]["exercise"] += 1
    manifest_path.write_text(json.dumps(manifest))
    commit_everything(instance, "another machine published a row")
    before = files_of(instance)

    for argv in (("upgrade", "--dry-run"), ("upgrade",)):
        run = run_coach(*argv)

        assert run.code == 5
        assert run.envelope["error"]["code"] == "store_behind_export"
        assert "exercise" in run.envelope["error"]["message"]
    assert files_of(instance) == before
    assert store_version(instance) == 1
    assert commit_subjects(instance)[0] == "another machine published a row"
