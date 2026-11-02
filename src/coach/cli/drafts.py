import itertools
from pathlib import Path

from coach.cli.declaration import Argument, Json
from coach.core.errors import Invalid

DRY_RUN = Argument(
    "--dry-run",
    "run the real write and roll it back: the result and ids the real run would give, or its "
    "violation; write nothing",
    takes_value=False,
)
DRY_RUN_OUTPUT: Json = {
    "dry_run": {"type": "boolean", "description": "dry run only"},
    "no_op": {"type": "boolean", "description": "dry run only: the Draft is already stored"},
}


def marked(result: Json, *, dry_run: bool, no_op: bool) -> Json:
    """A Draft verb's result, with `dry_run` and `no_op` on a dry run only."""
    return result | {"dry_run": True, "no_op": no_op} if dry_run else result


def read_draft(path: str) -> bytes:
    """The bytes of a Draft the agent wrote, relative to the working directory (ADR 0002)."""
    try:
        return (Path.cwd() / path).read_bytes()
    except OSError as error:
        raise Invalid(
            "invalid_argument", f"cannot read the Draft {path}: {error.strerror}"
        ) from error


def write_engine_draft(root: Path, *, today: str, kind: str, text: str, out: str | None) -> str:
    """Write a Draft the engine derived and return its path (verbs.md, "Drafts written by the
    engine"): the same content again is a no-op, other content at the default path takes the
    next free suffix, and an explicit `--out` holding other content is `draft_exists`."""
    data = text.encode("utf-8")
    if out is not None:
        path = Path.cwd() / out
        if path.exists() and path.read_bytes() != data:
            raise Invalid("draft_exists", f"{out} exists with other content; name another path")
        _write(path, data)
        return out
    for n in itertools.count(1):
        relative = f".coach/drafts/{today}-{kind}{'' if n == 1 else f'-{n}'}.toml"
        path = root / relative
        if not path.exists() or path.read_bytes() == data:
            _write(path, data)
            return relative
    raise AssertionError("unreachable")


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
