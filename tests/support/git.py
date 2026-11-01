import subprocess
from pathlib import Path

import pytest


def isolate_git(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """A committer identity and no global or system git config, so tests never read the user's."""
    for name, value in {
        "GIT_CONFIG_GLOBAL": str(home / "no-global-gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Athlete",
        "GIT_AUTHOR_EMAIL": "athlete@example.com",
        "GIT_COMMITTER_NAME": "Athlete",
        "GIT_COMMITTER_EMAIL": "athlete@example.com",
    }.items():
        monkeypatch.setenv(name, value)


def commit_subjects(root: Path) -> list[str]:
    listed = subprocess.run(
        ["git", "log", "--format=%s"], cwd=root, capture_output=True, text=True, check=True
    )
    return listed.stdout.splitlines()


def committed_files(root: Path) -> set[str]:
    listed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return set(listed.stdout.splitlines())
