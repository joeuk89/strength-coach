from contextlib import closing
from pathlib import Path

from coach.cli import git
from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.core.errors import Setup
from coach.services.publish import publish
from coach.store.export import on_disk

EXPORT = "export"
ATHLETE_FILES = ("coach.toml", "profile.md")
KIT = "kit"
WRITE_AUDIT = "hevy/writes.jsonl"
MESSAGE = "coach publish"


def run(call: Call) -> Outcome:
    assert call.instance is not None
    root = call.instance.root
    with closing(open_instance_store(call.instance)) as conn:
        publication = publish(conn, engine_version=call.engine_version)
    export_dir = call.instance.export_path
    current = on_disk(export_dir)
    written = sorted(name for name, text in publication.files.items() if current.get(name) != text)
    deleted = sorted(name for name in current if name not in publication.files)
    athlete_files = _athlete_files(root)
    summary: Json = {
        "written": [f"{EXPORT}/{name}" for name in written],
        "deleted": [f"{EXPORT}/{name}" for name in deleted],
        "athlete_files": athlete_files,
        "rows": dict(publication.rows),
    }
    if call.args.get("dry_run") is True:
        return Outcome({"dry_run": True, **summary})
    if not git.is_repo(root):
        raise Setup("git_failed", f"{root} is not a git repository; publish commits there")
    git.check_can_commit(root)
    export_dir.mkdir(exist_ok=True)
    for name in written:
        (export_dir / name).write_text(publication.files[name], encoding="utf-8")
    for name in deleted:
        (export_dir / name).unlink()
    paths = [EXPORT, *athlete_files]
    if (root / WRITE_AUDIT).is_file():
        paths.append(WRITE_AUDIT)
    commit = git.commit(root, paths, MESSAGE) if git.changed(root, paths) else None
    return Outcome({"commit": commit, **summary})


def _athlete_files(root: Path) -> list[str]:
    found = [name for name in ATHLETE_FILES if (root / name).is_file()]
    kit = root / KIT
    if kit.is_dir():
        found.extend(p.relative_to(root).as_posix() for p in kit.rglob("*") if p.is_file())
    return sorted(found)


DECLARATION = Declaration(
    name="publish",
    summary="Write export/ from the store and commit it with coach.toml, profile.md, kit/ and "
    "the Hevy write audit in one commit; nothing changed means no commit.",
    writes="git",
    needs_instance=True,
    arguments=(
        Argument(
            "--dry-run",
            "list the files publish would write, delete and commit, and the export rows per "
            "table; write and commit nothing",
            takes_value=False,
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "commit": {"type": ["string", "null"]},
            "dry_run": {"type": "boolean"},
            "written": {"type": "array", "items": {"type": "string"}},
            "deleted": {"type": "array", "items": {"type": "string"}},
            "athlete_files": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "object", "additionalProperties": {"type": "integer"}},
        },
        "required": ["written", "deleted", "athlete_files", "rows"],
    },
    run=run,
    examples=(
        Example(("publish", "--dry-run"), "The files publish would write and commit."),
        Example(("publish",), "Write the export and commit it."),
    ),
)
