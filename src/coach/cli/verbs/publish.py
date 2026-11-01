from contextlib import closing
from pathlib import Path

from coach.cli import export_dir as exported
from coach.cli import git, pages_dir
from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.core.errors import Setup
from coach.render.pages import PAGES_DIR, README
from coach.services.publish import publish

PROFILE = "profile.md"
ATHLETE_FILES = ("coach.toml", PROFILE)
KIT = "kit"
WRITE_AUDIT = "hevy/writes.jsonl"
MESSAGE = "coach publish"


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    root = call.instance.root
    profile = root / PROFILE
    with closing(open_instance_store(call.instance)) as conn:
        publication = publish(
            conn,
            call.clock,
            engine_version=call.engine_version,
            config=call.instance.config,
            kits=read_kit_files(call.instance),
            profile=profile.read_text(encoding="utf-8") if profile.is_file() else None,
        )
    export_dir = call.instance.export_path
    to_make = exported.changes(export_dir, publication.export.files)
    pages = pages_dir.changes(root, publication.pages)
    athlete_files = _athlete_files(root)
    summary: Json = {
        "written": [f"{exported.EXPORT}/{name}" for name in to_make.written] + list(pages.written),
        "deleted": [f"{exported.EXPORT}/{name}" for name in to_make.deleted] + list(pages.deleted),
        "athlete_files": athlete_files,
        "rows": dict(publication.export.rows),
    }
    if call.args.get("dry_run") is True:
        return Outcome({"dry_run": True, **summary})
    if not git.is_repo(root):
        raise Setup("git_failed", f"{root} is not a git repository; publish commits there")
    git.check_can_commit(root)
    exported.write(export_dir, publication.export.files, to_make)
    pages_dir.write(root, publication.pages, pages)
    paths = [
        path
        for path in (exported.EXPORT, PAGES_DIR, README, *ATHLETE_FILES, KIT, WRITE_AUDIT)
        if _has_files(root / path) or git.tracks(root, path)
    ]
    commit = git.commit(root, paths, MESSAGE) if git.changed(root, paths) else None
    return Outcome({"commit": commit, **summary})


def _has_files(path: Path) -> bool:
    return path.is_file() or (path.is_dir() and any(p.is_file() for p in path.rglob("*")))


def _athlete_files(root: Path) -> list[str]:
    found = [name for name in ATHLETE_FILES if (root / name).is_file()]
    kit = root / KIT
    if kit.is_dir():
        found.extend(p.relative_to(root).as_posix() for p in kit.rglob("*") if p.is_file())
    return sorted(found)


DECLARATION = Declaration(
    name="publish",
    summary="Write export/, pages/ and README.md from the store and commit them with "
    "coach.toml, profile.md, kit/ and the Hevy write audit in one commit; nothing changed means "
    "no commit.",
    writes="git",
    needs_instance=True,
    arguments=(
        Argument(
            "--dry-run",
            "list the export files and pages publish would write and delete, the files it would "
            "commit, and the export rows per table; write and commit nothing",
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
        Example(("publish",), "Write the export and the pages and commit them."),
    ),
)
