"""The generated, engine-owned files of an instance (ADR 0013): `init` writes them, `status`
warns when they drift, `upgrade` rewrites them."""

from pathlib import Path

from coach.cli import registry
from coach.render.instance_files import claude_md, settings_json

ASKED = ("hevy", "git")


def generated_files(version: str) -> dict[str, str]:
    asked = [d.name for d in registry.declarations() if d.writes in ASKED]
    return {".claude/settings.json": settings_json(asked), "CLAUDE.md": claude_md(version)}


def drifted(root: Path, version: str) -> tuple[str, ...]:
    """The generated files that differ from what engine `version` generates, a missing one too."""
    return tuple(
        relative
        for relative, text in generated_files(version).items()
        if _read(root / relative) != text
    )


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None
