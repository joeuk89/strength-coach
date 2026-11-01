import shutil
from pathlib import Path

import pytest
from support.cli import run_coach
from support.git import commit_subjects, committed_files, isolate_git
from support.scenarios import a_history, a_session

from coach.cli import app
from coach.store.connection import open_store

ENGINE = "0.3.0"


@pytest.fixture(scope="module")
def initialised(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One `coach init` per module, copied into each test; init alone costs a tenth of a second."""
    home = tmp_path_factory.mktemp("home")
    root = home / "athlete"
    root.mkdir()
    with pytest.MonkeyPatch.context() as patch:
        isolate_git(patch, home)
        patch.setattr(app, "engine_version", lambda: ENGINE)
        patch.chdir(root)
        assert run_coach("init", "--defaults").code == 0
    with open_store(root / ".coach" / "coach.db") as conn:
        conn.execute("DELETE FROM exercise")
        a_history(conn)
    conn.close()
    return root


@pytest.fixture
def instance(initialised: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    isolate_git(monkeypatch, tmp_path)
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = tmp_path / "athlete"
    shutil.copytree(initialised, root)
    monkeypatch.chdir(root)
    return root


def test_publish_twice_on_an_unchanged_store_makes_one_commit_then_none(instance: Path) -> None:
    first = run_coach("publish")
    second = run_coach("publish")

    assert first.code == 0, first.stdout
    assert second.code == 0, second.stdout
    assert commit_subjects(instance) == ["coach publish", f"coach init v{ENGINE}"]
    assert first.envelope["result"]["commit"] is not None
    assert second.envelope["result"]["commit"] is None
    assert second.envelope["result"]["written"] == []


def test_publish_commits_the_export_with_rows_per_table(instance: Path) -> None:
    run = run_coach("publish")

    result = run.envelope["result"]
    assert result["rows"]["workout"] == 2
    assert result["rows"]["logged_set"] == 14
    assert "export/manifest.json" in result["written"]
    assert "export/workout.jsonl" in result["written"]
    assert {"export/manifest.json", "export/workout.jsonl"} <= committed_files(instance)


def test_publish_commits_the_athlete_authored_files_and_the_write_audit(instance: Path) -> None:
    (instance / "profile.md").write_text("# Athlete\n", encoding="utf-8")
    (instance / "kit" / "home.json").write_text("{}\n", encoding="utf-8")
    (instance / "hevy").mkdir()
    (instance / "hevy" / "writes.jsonl").write_text("{}\n", encoding="utf-8")
    with (instance / "coach.toml").open("a", encoding="utf-8") as toml:
        toml.write("\n")

    run = run_coach("publish")

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["athlete_files"] == ["coach.toml", "kit/home.json", "profile.md"]
    assert {"profile.md", "kit/home.json", "hevy/writes.jsonl"} <= committed_files(instance)
    status = run_coach("status")
    assert status.envelope["result"]["export"]["behind_store"] is False


def test_an_athlete_edit_alone_is_committed_by_the_next_publish(instance: Path) -> None:
    run_coach("publish")
    (instance / "profile.md").write_text("# Athlete\n", encoding="utf-8")

    run = run_coach("publish")

    assert run.envelope["result"]["commit"] is not None
    assert run.envelope["result"]["written"] == []
    assert "profile.md" in committed_files(instance)


def test_a_dry_run_lists_files_and_row_counts_and_writes_and_commits_nothing(
    instance: Path,
) -> None:
    run = run_coach("publish", "--dry-run")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["dry_run"] is True
    assert "commit" not in result
    assert result["rows"]["workout"] == 2
    assert "export/workout.jsonl" in result["written"]
    assert result["athlete_files"] == ["coach.toml"]
    assert not (instance / "export").exists()
    assert commit_subjects(instance) == [f"coach init v{ENGINE}"]


def test_a_new_row_after_publish_is_written_and_committed_by_the_next(instance: Path) -> None:
    run_coach("publish")
    with open_store(instance / ".coach" / "coach.db") as conn:
        a_session(conn, "push_b")
    conn.close()

    run = run_coach("publish")

    assert run.envelope["result"]["written"] == ["export/manifest.json", "export/session.jsonl"]
    assert len(commit_subjects(instance)) == 3


def test_an_export_file_for_no_table_is_deleted(instance: Path) -> None:
    run_coach("publish")
    (instance / "export" / "block.jsonl").write_text("", encoding="utf-8")

    run = run_coach("publish")

    assert run.envelope["result"]["deleted"] == ["export/block.jsonl"]
    assert not (instance / "export" / "block.jsonl").exists()


def test_publish_outside_a_git_repository_stops_with_git_failed(instance: Path) -> None:
    shutil.rmtree(instance / ".git")

    run = run_coach("publish")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "git_failed"
    assert not (instance / "export").exists()


def test_publish_clears_store_behind_export(instance: Path) -> None:
    run_coach("publish")
    database = instance / ".coach" / "coach.db"
    database.unlink()
    open_store(database).close()
    assert run_coach("status").envelope["result"]["export"]["store_behind_export"] is True

    assert run_coach("publish").code == 0

    assert run_coach("status").envelope["result"]["export"] == {
        "behind_store": False,
        "store_behind_export": False,
    }


def test_a_deleted_kit_file_is_removed_by_the_next_publish(instance: Path) -> None:
    (instance / "kit" / "home.json").write_text("{}\n", encoding="utf-8")
    (instance / "kit" / "gym.json").write_text("{}\n", encoding="utf-8")
    run_coach("publish")
    (instance / "kit" / "gym.json").unlink()

    run = run_coach("publish")

    assert run.envelope["result"]["commit"] is not None
    assert "kit/gym.json" not in committed_files(instance)
    assert "kit/home.json" in committed_files(instance)


def test_a_deleted_profile_is_removed_by_the_next_publish(instance: Path) -> None:
    (instance / "profile.md").write_text("# Athlete\n", encoding="utf-8")
    run_coach("publish")
    (instance / "profile.md").unlink()

    run = run_coach("publish")

    assert run.envelope["result"]["commit"] is not None
    assert "profile.md" not in committed_files(instance)
