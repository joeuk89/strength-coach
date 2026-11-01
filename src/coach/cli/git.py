import subprocess
from collections.abc import Sequence
from pathlib import Path


def is_repo(root: Path) -> bool:
    return (root / ".git").exists()


def init(root: Path) -> None:
    _git(root, "init", "--quiet")


def commit(root: Path, paths: Sequence[str], message: str) -> str:
    """Commit exactly `paths`, whatever else is staged, and return the commit hash."""
    _git(root, "add", "--", *paths)
    _git(root, "commit", "--quiet", "--message", message, "--", *paths)
    return _git(root, "rev-parse", "HEAD").strip()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {completed.stderr.strip()}")
    return completed.stdout
