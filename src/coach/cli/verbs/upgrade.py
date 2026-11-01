from contextlib import closing
from pathlib import Path

from coach.cli import export_dir as exported
from coach.cli import git
from coach.cli.declaration import (
    Argument,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Json,
    Outcome,
)
from coach.cli.generated import drifted, generated_files
from coach.cli.instance import CONFIG, refuse_tables_behind_the_export
from coach.core.engine_pin import notes_between
from coach.core.errors import Setup
from coach.render.instance_files import with_pin
from coach.services.upgrade import Upgraded, upgrade
from coach.store.chain import engine
from coach.store.connection import copy_to_memory, open_store_behind, schema_version


def run(call: InstanceCall) -> Outcome:
    instance = call.instance
    root = instance.root
    running = call.engine_version
    regenerated = drifted(root, running)
    with closing(open_store_behind(instance.store_path)) as live:
        version = schema_version(live)
        if running == instance.pin and not engine().pending(version) and not regenerated:
            return Outcome(_unchanged(instance.pin, version))
        refuse_tables_behind_the_export(instance, live)
        _refuse_a_dirty_tree(root)
        if call.args.get("dry_run") is True:
            with closing(copy_to_memory(live)) as copy:
                upgraded = upgrade(copy, engine_version=running)
            to_make = exported.changes(instance.export_path, upgraded.export.files)
            summary = _summary(instance.pin, running, upgraded, regenerated, to_make)
            return Outcome({"dry_run": True, **summary})
        git.check_can_commit(root)
        upgraded = upgrade(live, engine_version=running)
    to_make = exported.changes(instance.export_path, upgraded.export.files)
    exported.write(instance.export_path, upgraded.export.files, to_make)
    _regenerate(root, running, regenerated)
    if running != instance.pin:
        config = root / CONFIG
        config.write_text(with_pin(config.read_text(encoding="utf-8"), running), encoding="utf-8")
    summary = _summary(instance.pin, running, upgraded, regenerated, to_make)
    paths = [exported.EXPORT, CONFIG, *generated_files(running)]
    commit = (
        git.commit(root, paths, f"coach upgrade v{running}") if git.changed(root, paths) else None
    )
    return Outcome({**summary, "commit": commit})


def _refuse_a_dirty_tree(root: Path) -> None:
    if not git.is_repo(root):
        raise Setup("git_failed", f"{root} is not a git repository; upgrade commits there")
    dirty = git.dirty(root)
    if dirty:
        raise Setup(
            "git_tree_dirty",
            f"upgrade commits on a clean tree and {', '.join(dirty[:5])} "
            f"{'is' if len(dirty) == 1 else 'are'} changed; commit or discard them, or run "
            "`coach publish`, then upgrade",
        )


def _regenerate(root: Path, version: str, relatives: tuple[str, ...]) -> None:
    texts = generated_files(version)
    for relative in relatives:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(texts[relative], encoding="utf-8")


def _summary(
    pin: str,
    running: str,
    upgraded: Upgraded,
    regenerated: tuple[str, ...],
    to_make: exported.ExportChanges,
) -> Json:
    moved = [CONFIG] if running != pin else []
    return {
        "from": pin,
        "to": running,
        "schema_version": {"from": upgraded.from_version, "to": upgraded.to_version},
        "migrations": list(upgraded.migrations),
        "catalogue_added": list(upgraded.catalogue_added),
        "files": [*regenerated, *moved, *to_make.paths()],
        "notes": list(notes_between(pin, running)),
    }


def _unchanged(pin: str, version: int) -> Json:
    return {
        "from": pin,
        "to": pin,
        "schema_version": {"from": version, "to": version},
        "migrations": [],
        "catalogue_added": [],
        "files": [],
        "notes": [],
        "commit": None,
    }


DECLARATION = Declaration(
    name="upgrade",
    summary="Bring the instance up to the installed engine: migrate the store, merge the "
    "catalogue, rewrite the export and the generated files, move the pin, one commit.",
    writes="git",
    moves_pin=True,
    arguments=(
        Argument(
            "--dry-run",
            "list the migrations upgrade would run, the files it would write and the "
            "migration notes; write and commit nothing",
            takes_value=False,
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "from": {"type": "string"},
            "to": {"type": "string"},
            "schema_version": {
                "type": "object",
                "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}},
                "required": ["from", "to"],
            },
            "migrations": {"type": "array", "items": {"type": "string"}},
            "catalogue_added": {"type": "array", "items": {"type": "string"}},
            "files": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
            "dry_run": {"type": "boolean"},
            "commit": {"type": ["string", "null"]},
        },
        "required": [
            "from",
            "to",
            "schema_version",
            "migrations",
            "catalogue_added",
            "files",
            "notes",
        ],
    },
    run=InInstance(run),
    examples=(
        Example(("upgrade", "--dry-run"), "What upgrade would migrate and write."),
        Example(("upgrade",), "Upgrade the instance and commit."),
    ),
)
