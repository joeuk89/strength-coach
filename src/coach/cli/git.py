import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

from coach.core.errors import Setup


def is_repo(root: Path) -> bool:
    return (root / ".git").exists()


def check_can_commit(root: Path) -> None:
    """Raise Setup unless git is on the PATH and knows who is committing."""
    for ident in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        completed = _run(root, "var", ident)
        if completed.returncode != 0:
            raise Setup(
                "git_identity_missing",
                "git does not know who is committing; set it with "
                "`git config --global user.name <name>` and "
                "`git config --global user.email <email>`, then run init again",
            )


def init(root: Path) -> None:
    _git(root, "init", "--quiet")


def changed(root: Path, paths: Sequence[str]) -> bool:
    """Whether git sees any change, untracked files included, under `paths`."""
    return bool(_git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths))


def dirty(root: Path) -> tuple[str, ...]:
    """Every path git sees changed or untracked anywhere in the tree."""
    listed = _git(root, "status", "--porcelain", "--untracked-files=all")
    return tuple(line[3:] for line in listed.splitlines())


def tracks(root: Path, path: str) -> bool:
    """Whether git tracks `path` or any file under it."""
    return bool(_git(root, "ls-files", "--", path))


def commit(root: Path, paths: Sequence[str], message: str) -> str:
    """Commit exactly `paths`, whatever else is staged, and return the commit hash."""
    try:
        # A global excludes file may ignore .claude/; these paths are committed regardless.
        _git(root, "add", "--force", "--", *paths)
        _git(root, "commit", "--quiet", "--message", message, "--", *paths)
    except Setup as error:
        by_hand = f"git add --force -- {shlex.join(paths)} && git commit -m {shlex.quote(message)}"
        raise Setup(
            "git_commit_failed",
            f"the files are written but not committed: {error.message}; fix that, then "
            f"finish by hand with `{by_hand}`",
        ) from error
    return _git(root, "rev-parse", "HEAD").strip()


def _git(root: Path, *args: str) -> str:
    completed = _run(root, *args)
    if completed.returncode != 0:
        raise Setup("git_failed", f"git {args[0]} failed: {completed.stderr.strip()}")
    return completed.stdout


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        raise Setup("git_unavailable", "git is not on the PATH; install git") from error
