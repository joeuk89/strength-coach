import io
import json
import os
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.hevy_payloads import a_workout
from support.instances import an_instance
from support.terminal import typed

from coach.cli import app
from coach.cli.declaration import MakeClient
from coach.cli.registry import declarations
from coach.core.clock import Clock
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

RELEASE = "0.3.0"
DEV = "0.4.0.dev0"
WORKOUT = "10000000-0000-4000-8000-00000000000a"

INIT_TREE = {
    ".claude",
    ".claude/settings.json",
    ".coach",
    ".coach/coach.db",
    ".coach/drafts",
    ".gitignore",
    "CLAUDE.md",
    "coach.toml",
    "kit",
}


@pytest.fixture(autouse=True)
def empty_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    for name, value in {
        "GIT_CONFIG_GLOBAL": str(tmp_path.parent / "no-global-gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Athlete",
        "GIT_AUTHOR_EMAIL": "athlete@example.com",
        "GIT_COMMITTER_NAME": "Athlete",
        "GIT_COMMITTER_EMAIL": "athlete@example.com",
    }.items():
        monkeypatch.setenv(name, value)
    return tmp_path


@pytest.fixture
def release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: RELEASE)


@pytest.fixture
def dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app, "engine_version", lambda: DEV)


def tree(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if ".git" not in path.relative_to(root).parts
    }


def commit_log(root: Path) -> list[str]:
    return (root / ".git" / "logs" / "HEAD").read_text(encoding="utf-8").splitlines()


def coach_toml(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "coach.toml").read_text(encoding="utf-8"))


def test_init_defaults_writes_exactly_the_tree_in_one_commit_and_status_runs(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--defaults")

    assert run.code == 0, run.stdout
    assert tree(empty_directory) == INIT_TREE
    (entry,) = commit_log(empty_directory)
    assert entry.endswith(f"commit (initial): coach init v{RELEASE}")
    result = run.envelope["result"]
    assert result["pin"] == RELEASE
    assert result["commit"] in entry
    assert result["committed"] == [".gitignore", ".claude/settings.json", "CLAUDE.md", "coach.toml"]
    assert "push" in result["next"]
    assert run_coach("status").code == 0


def test_init_defaults_takes_every_default(empty_directory: Path, release: None) -> None:
    run_coach("init", "--defaults", env={"TZ": "Asia/Tokyo"})

    assert coach_toml(empty_directory) == {
        "engine": {"version": RELEASE},
        "athlete": {
            "units": "kg",
            "bodyweight_units": "kg",
            "week_starts": "monday",
            "timezone": "Asia/Tokyo",
            "available_days": [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ],
            "session_minutes": 60,
            "checkin_cadence_days": 7,
        },
    }


def test_every_answer_has_a_flag(empty_directory: Path, release: None) -> None:
    run = run_coach(
        "init",
        "--units", "lb",
        "--bodyweight-units", "kg",
        "--week-starts", "sunday",
        "--timezone", "America/New_York",
        "--available-days", "sunday, tuesday,thursday",
        "--session-minutes", "45",
        "--checkin-cadence-days", "14",
        "--hevy", "no",
    )  # fmt: skip

    assert run.code == 0, run.stdout
    assert coach_toml(empty_directory)["athlete"] == {
        "units": "lb",
        "bodyweight_units": "kg",
        "week_starts": "sunday",
        "timezone": "America/New_York",
        "available_days": ["sunday", "tuesday", "thursday"],
        "session_minutes": 45,
        "checkin_cadence_days": 14,
    }


def serving(hevy: FakeHevy) -> MakeClient:
    def make_client(key: str, audit_path: Path, clock: Clock) -> FakeHevy:
        return hevy

    return make_client


def test_a_hevy_key_turns_hevy_on_and_lands_in_the_gitignored_env(
    empty_directory: Path, release: None
) -> None:
    hevy = serving(FakeHevy(FixedClock()))

    run = run_coach("init", "--defaults", "--hevy-key", "test-key-not-real", make_client=hevy)

    assert run.code == 0, run.stdout
    assert coach_toml(empty_directory)["hevy"] == {}
    assert (empty_directory / ".env").read_text() == "HEVY_API_KEY=test-key-not-real\n"
    assert tree(empty_directory) == INIT_TREE | {".env"}
    assert ".env" not in run.envelope["result"]["committed"]
    assert "test-key-not-real" not in run.stdout
    assert run_coach("status").envelope["result"]["hevy"]["on"] is True


def test_init_with_a_hevy_key_pulls_the_whole_history_into_the_store(
    empty_directory: Path, release: None
) -> None:
    clock = FixedClock()
    hevy = FakeHevy(clock, workouts=[a_workout(WORKOUT)])

    run = run_coach("init", "--defaults", "--hevy-key", "k", clock=clock, make_client=serving(hevy))

    assert run.code == 0, run.stdout
    pull = run.envelope["result"]["pull"]
    assert (pull["kind"], pull["workouts"]["new"]) == ("full", 1)
    status = run_coach("status", clock=clock).envelope["result"]
    assert status["workouts"] == {"hevy": 1, "manual": 0}


def test_init_with_hevy_unreachable_leaves_the_instance_written_and_exits_4(
    empty_directory: Path, release: None
) -> None:
    clock = FixedClock()
    down = FakeHevy(clock, workouts=[a_workout(WORKOUT)])
    down.fail_next_get()

    run = run_coach("init", "--defaults", "--hevy-key", "k", clock=clock, make_client=serving(down))

    assert (run.code, run.envelope["error"]["code"]) == (4, "hevy_unreachable")
    assert "the instance is written and committed" in run.envelope["error"]["message"]
    assert tree(empty_directory) == INIT_TREE | {".env"}
    assert len(commit_log(empty_directory)) == 1
    up = FakeHevy(clock, workouts=[a_workout(WORKOUT)])
    checkin = run_coach("checkin", "open", clock=clock, make_client=serving(up))
    pull = checkin.envelope["result"]["pull"]
    assert (pull["kind"], pull["workouts"]["new"]) == ("full", 1)


def no_hevy() -> MakeClient:
    return serving(FakeHevy(FixedClock()))


def test_short_day_names_on_the_flags_are_written_as_full_names(
    empty_directory: Path, release: None
) -> None:
    run = run_coach(
        "init", "--defaults", "--available-days", "mon,tue,thu", "--hevy", "no",
        make_client=no_hevy(),
    )  # fmt: skip

    assert run.code == 0, run.stdout
    athlete = coach_toml(empty_directory)["athlete"]
    assert isinstance(athlete, dict)
    assert athlete["available_days"] == ["monday", "tuesday", "thursday"]


@pytest.mark.parametrize("written", ["mon", "Monday"])
def test_week_starts_takes_a_short_or_capitalised_day(
    empty_directory: Path, release: None, written: str
) -> None:
    run = run_coach("init", "--defaults", "--week-starts", written, make_client=no_hevy())

    assert run.code == 0, run.stdout
    athlete = coach_toml(empty_directory)["athlete"]
    assert isinstance(athlete, dict)
    assert athlete["week_starts"] == "monday"


def test_a_day_named_in_both_forms_is_refused_as_named_twice(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--defaults", "--available-days", "mon,monday", make_client=no_hevy())

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
    assert "names a weekday twice" in run.envelope["error"]["message"]
    assert tree(empty_directory) == set()


def test_a_bad_day_is_refused_showing_both_accepted_forms(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--defaults", "--available-days", "mo", make_client=no_hevy())

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")
    message = run.envelope["error"]["message"]
    assert message.startswith("--available-days: ")
    assert "monday or mon" in message
    assert tree(empty_directory) == set()


def test_the_prompt_takes_short_day_names(
    empty_directory: Path, release: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = ["", "", "Sun", "Asia/Tokyo", "mon, wed,FRI", "", "", "no", "y"]
    monkeypatch.setattr(sys, "stdin", typed(*answers))

    run = run_coach("init", make_client=no_hevy())

    assert run.code == 0, run.stdout
    athlete = coach_toml(empty_directory)["athlete"]
    assert isinstance(athlete, dict)
    assert (athlete["week_starts"], athlete["available_days"]) == (
        "sunday",
        ["monday", "wednesday", "friday"],
    )


def test_a_hevy_key_beside_an_existing_env_stops_before_a_file_is_written(
    empty_directory: Path, release: None
) -> None:
    (empty_directory / ".env").write_text("OTHER=1\n")

    run = run_coach("init", "--defaults", "--hevy-key", "test-key-not-real")

    assert (run.code, run.envelope["error"]["code"]) == (5, "env_file_exists")
    assert tree(empty_directory) == {".env"}
    assert (empty_directory / ".env").read_text() == "OTHER=1\n"


def test_a_github_token_lands_in_the_gitignored_env_and_leaves_hevy_off(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--defaults", "--github-token", "test-token-not-real")

    assert run.code == 0, run.stdout
    assert "hevy" not in coach_toml(empty_directory)
    assert (empty_directory / ".env").read_text() == "COACH_GITHUB_TOKEN=test-token-not-real\n"
    assert ".env" not in run.envelope["result"]["committed"]
    assert "test-token-not-real" not in run.stdout


def test_a_github_token_is_written_beside_the_hevy_key(
    empty_directory: Path, release: None
) -> None:
    hevy = serving(FakeHevy(FixedClock()))

    run = run_coach(
        "init",
        "--defaults",
        "--hevy-key",
        "test-key-not-real",
        "--github-token",
        "test-token-not-real",
        make_client=hevy,
    )

    assert run.code == 0, run.stdout
    assert (empty_directory / ".env").read_text() == (
        "HEVY_API_KEY=test-key-not-real\nCOACH_GITHUB_TOKEN=test-token-not-real\n"
    )


def test_a_github_token_beside_an_existing_env_stops_before_a_file_is_written(
    empty_directory: Path, release: None
) -> None:
    (empty_directory / ".env").write_text("OTHER=1\n")

    run = run_coach("init", "--defaults", "--github-token", "test-token-not-real")

    assert (run.code, run.envelope["error"]["code"]) == (5, "env_file_exists")
    assert (empty_directory / ".env").read_text() == "OTHER=1\n"


def test_hevy_without_a_key_writes_the_table_and_no_env(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--defaults", "--hevy", "yes")

    assert run.code == 0, run.stdout
    assert coach_toml(empty_directory)["hevy"] == {}
    assert not (empty_directory / ".env").exists()
    assert "pull" not in run.envelope["result"]


def test_the_generated_settings_ask_on_exactly_the_verbs_declared_hevy_git_or_github(
    empty_directory: Path, release: None
) -> None:
    run_coach("init", "--defaults")

    settings = json.loads((empty_directory / ".claude" / "settings.json").read_text())
    asked = sorted(d.name for d in declarations() if d.writes in ("hevy", "git", "github"))
    assert settings["permissions"]["ask"] == [f"Bash(coach {name}:*)" for name in asked]
    assert "Bash(*api.hevyapp.com/v1/workouts*)" in settings["permissions"]["deny"]


def test_the_generated_claude_md_is_under_forty_lines(empty_directory: Path, release: None) -> None:
    run_coach("init", "--defaults")

    assert len((empty_directory / "CLAUDE.md").read_text().splitlines()) < 40


def test_dry_run_prints_the_tree_and_writes_nothing(empty_directory: Path, release: None) -> None:
    run = run_coach("init", "--defaults", "--dry-run")

    assert run.code == 0, run.stdout
    assert tree(empty_directory) == set()
    assert not (empty_directory / ".git").exists()
    result = run.envelope["result"]
    assert result["dry_run"] is True
    assert set(result["files"]) == {
        ".gitignore",
        ".claude/settings.json",
        "CLAUDE.md",
        "coach.toml",
        "kit/",
        ".coach/drafts/",
        ".coach/coach.db",
    }
    assert result["git_init"] is True
    assert "commit" not in result


def test_init_on_an_instance_stops_with_instance_exists(
    empty_directory: Path, release: None
) -> None:
    an_instance(empty_directory, pin=RELEASE)
    before = tree(empty_directory)
    toml = (empty_directory / "coach.toml").read_text()

    run = run_coach("init", "--defaults")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "instance_exists"
    assert (empty_directory / "coach.toml").read_text() == toml
    assert tree(empty_directory) == before


@pytest.mark.parametrize("owned", ["CLAUDE.md", ".coach", "export", "pages", "README.md"])
def test_any_engine_owned_path_stops_init_with_instance_exists(
    empty_directory: Path, release: None, owned: str
) -> None:
    (empty_directory / owned).mkdir()

    run = run_coach("init", "--defaults", "--dry-run")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "instance_exists"


def test_init_writes_beside_what_is_there_and_keeps_the_athletes_gitignore(
    empty_directory: Path, release: None
) -> None:
    (empty_directory / "notes.txt").write_text("mine\n")
    (empty_directory / ".gitignore").write_text("scratch/\n.env\n")

    run = run_coach("init", "--defaults")

    assert run.code == 0, run.stdout
    assert (empty_directory / "notes.txt").read_text() == "mine\n"
    assert (empty_directory / ".gitignore").read_text().splitlines() == [
        "scratch/",
        ".env",
        ".coach/",
        ".claude/settings.local.json",
    ]


def test_a_dev_build_refuses_without_a_pin(empty_directory: Path, dev: None) -> None:
    run = run_coach("init", "--defaults")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "engine_pin_required"
    assert tree(empty_directory) == set()


def test_a_dev_build_writes_the_release_it_is_pinned_to(empty_directory: Path, dev: None) -> None:
    run = run_coach("init", "--defaults", "--pin", "0.3.0")

    assert run.code == 0, run.stdout
    assert coach_toml(empty_directory)["engine"] == {"version": "0.3.0"}
    assert commit_log(empty_directory)[0].endswith("coach init v0.3.0")
    status = run_coach("status")
    assert status.code == 0
    assert [w["code"] for w in status.envelope["warnings"]] == ["engine_pin_dev"]


def test_a_release_build_refuses_a_pin_other_than_itself(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--defaults", "--pin", "0.2.0")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "engine_pin_mismatch"
    assert tree(empty_directory) == set()


def test_a_release_build_accepts_its_own_version_as_the_pin(
    empty_directory: Path, release: None
) -> None:
    assert run_coach("init", "--defaults", "--dry-run", "--pin", RELEASE).code == 0


@pytest.mark.parametrize("pin", ["0.3.0.dev1", "latest", "1.2"])
def test_a_pin_that_is_not_a_release_is_invalid(empty_directory: Path, dev: None, pin: str) -> None:
    run = run_coach("init", "--defaults", "--pin", pin)

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize(
    "flags",
    [
        ("--units", "stone"),
        ("--session-minutes", "an hour"),
        ("--available-days", "monday,someday"),
        ("--timezone", "Mars/Olympus"),
        ("--hevy", "maybe"),
        ("--hevy", "no", "--hevy-key", "k"),
    ],
)
def test_a_bad_answer_on_a_flag_is_invalid_and_writes_nothing(
    empty_directory: Path, release: None, flags: tuple[str, ...]
) -> None:
    run = run_coach("init", "--defaults", *flags)

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
    assert tree(empty_directory) == set()


def test_without_a_terminal_or_defaults_a_missing_answer_names_its_flag(
    empty_directory: Path, release: None
) -> None:
    run = run_coach("init", "--units", "kg")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"
    assert "--session-minutes" in run.envelope["error"]["message"]
    assert "--units" not in run.envelope["error"]["message"]
    assert tree(empty_directory) == set()


def test_on_a_terminal_init_asks_each_fact_and_confirms_the_files(
    empty_directory: Path, release: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = ["lb", "", "stone", "sunday", "Asia/Tokyo", "monday,friday", "50", "", "no", "y"]
    monkeypatch.setattr(sys, "stdin", typed(*answers))

    run = run_coach("init")

    assert run.code == 0, run.stdout
    assert coach_toml(empty_directory)["athlete"] == {
        "units": "lb",
        "bodyweight_units": "kg",
        "week_starts": "sunday",
        "timezone": "Asia/Tokyo",
        "available_days": ["monday", "friday"],
        "session_minutes": 50,
        "checkin_cadence_days": 7,
    }
    assert "stone" in run.stderr
    assert "coach.toml" in run.stderr
    assert run.stdout.count("\n") == 1


def test_saying_no_at_the_terminal_writes_nothing(
    empty_directory: Path, release: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", typed("n"))

    run = run_coach("init", "--defaults")

    assert run.code == 0
    assert run.envelope["result"]["declined"] is True
    assert tree(empty_directory) == set()


def global_gitconfig(text: str) -> None:
    Path(os.environ["GIT_CONFIG_GLOBAL"]).write_text(text, encoding="utf-8")


def committed_paths(root: Path) -> set[str]:
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return set(listed.stdout.splitlines())


def test_init_commits_the_settings_a_global_excludes_file_ignores(
    empty_directory: Path, release: None
) -> None:
    excludes = empty_directory.parent / "global-excludes"
    excludes.write_text(".claude/\n", encoding="utf-8")
    global_gitconfig(f"[core]\n\texcludesFile = {excludes}\n")

    run = run_coach("init", "--defaults")

    assert run.code == 0, run.stdout
    assert committed_paths(empty_directory) == {
        ".gitignore",
        ".claude/settings.json",
        "CLAUDE.md",
        "coach.toml",
    }


def test_init_without_a_git_identity_stops_before_writing(
    empty_directory: Path, release: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("NAME", "EMAIL"):
        monkeypatch.delenv(f"GIT_AUTHOR_{name}")
        monkeypatch.delenv(f"GIT_COMMITTER_{name}")
    global_gitconfig("[user]\n\tuseConfigOnly = true\n")

    run = run_coach("init", "--defaults")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "git_identity_missing"
    assert "user.email" in run.envelope["error"]["message"]
    assert tree(empty_directory) == set()
    assert not (empty_directory / ".git").exists()


def test_init_without_git_on_the_path_stops_before_writing(
    empty_directory: Path, release: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(empty_directory.parent / "no-git-here"))

    run = run_coach("init", "--defaults")

    assert run.code == 5
    assert run.envelope["error"]["code"] == "git_unavailable"
    assert tree(empty_directory) == set()


def test_a_commit_git_refuses_is_a_setup_error_that_says_how_to_finish(
    empty_directory: Path, release: None
) -> None:
    hooks = empty_directory.parent / "hooks"
    hooks.mkdir()
    pre_commit = hooks / "pre-commit"
    pre_commit.write_text("#!/bin/sh\necho hook says no >&2\nexit 1\n", encoding="utf-8")
    pre_commit.chmod(0o755)
    global_gitconfig(f"[core]\n\thooksPath = {hooks}\n")

    run = run_coach("init", "--defaults")

    assert run.code == 5
    error = run.envelope["error"]
    assert error["code"] == "git_commit_failed"
    assert "hook says no" in error["message"]
    assert f"git commit -m 'coach init v{RELEASE}'" in error["message"]


def test_init_seeds_the_store_with_every_catalogue_row(
    empty_directory: Path, release: None
) -> None:
    catalogue = open_store(":memory:")
    seed_catalogue(catalogue)

    run_coach("init", "--defaults")

    store = sqlite3.connect(empty_directory / ".coach" / "coach.db")
    seeded = store.execute("SELECT * FROM exercise ORDER BY id").fetchall()
    sources = store.execute("SELECT DISTINCT source FROM exercise").fetchall()
    bench = store.execute(
        "SELECT name, load_mode, equipment_kind FROM exercise WHERE id = 'bb_bench_press'"
    ).fetchone()
    store.close()
    assert seeded == catalogue.execute("SELECT * FROM exercise ORDER BY id").fetchall()
    assert sources == [("catalogue",)]
    assert bench == ("Bench Press (Barbell)", "total", "barbell")
