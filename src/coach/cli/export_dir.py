from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from coach.store.export import on_disk

EXPORT = "export"


@dataclass(frozen=True)
class ExportChanges:
    """File names inside `export/` that a fresh export writes and deletes."""

    written: tuple[str, ...]
    deleted: tuple[str, ...]

    def paths(self) -> list[str]:
        return [f"{EXPORT}/{name}" for name in (*self.written, *self.deleted)]


def changes(export_dir: Path, files: Mapping[str, str]) -> ExportChanges:
    current = on_disk(export_dir)
    return ExportChanges(
        written=tuple(sorted(name for name, text in files.items() if current.get(name) != text)),
        deleted=tuple(sorted(name for name in current if name not in files)),
    )


def write(export_dir: Path, files: Mapping[str, str], to_make: ExportChanges) -> None:
    export_dir.mkdir(exist_ok=True)
    for name in to_make.written:
        (export_dir / name).write_text(files[name], encoding="utf-8")
    for name in to_make.deleted:
        (export_dir / name).unlink()
