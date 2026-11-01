from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from coach.render.pages import PAGES_DIR, README


@dataclass(frozen=True)
class PageChanges:
    """Paths from the instance root that a publish writes, and files under `pages/` it did not
    render, which it deletes."""

    written: tuple[str, ...]
    deleted: tuple[str, ...]


def changes(root: Path, pages: Mapping[str, str]) -> PageChanges:
    current = _on_disk(root)
    return PageChanges(
        written=tuple(sorted(path for path, text in pages.items() if current.get(path) != text)),
        deleted=tuple(sorted(path for path in current if path not in pages)),
    )


def write(root: Path, pages: Mapping[str, str], to_make: PageChanges) -> None:
    for path in to_make.written:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(pages[path], encoding="utf-8", newline="\n")
    for path in to_make.deleted:
        (root / path).unlink()


def _on_disk(root: Path) -> dict[str, str | None]:
    found: dict[str, str | None] = {
        p.relative_to(root).as_posix(): _text(p)
        for p in (root / PAGES_DIR).rglob("*")
        if p.is_file()
    }
    readme = root / README
    if readme.is_file():
        found[README] = _text(readme)
    return found


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
