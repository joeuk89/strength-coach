"""Reading a plate-pool location's kit files; the inventory is hashed, never parsed (ADR 0021)."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from coach.cli.declaration import Instance
from coach.core.config import PlatePoolLocation
from coach.core.kit import KitFiles, require_current_tables


def read_kit_files(instance: Instance) -> tuple[KitFiles, ...]:
    return tuple(
        _read(instance.root / "kit", location)
        for location in instance.config.locations
        if isinstance(location, PlatePoolLocation)
    )


def require_current_kit(instance: Instance) -> None:
    """`kit_tables_stale` for `plan draft` and `program adopt`, before they round."""
    for files in read_kit_files(instance):
        require_current_tables(files)


def _read(kit_dir: Path, location: PlatePoolLocation) -> KitFiles:
    inventory = _bytes(kit_dir / f"{location.kit}.json")
    return KitFiles(
        location=location.name,
        kit=location.kit,
        tables=_tables(kit_dir / f"{location.kit}.achievable.json"),
        inventory_sha256=None if inventory is None else hashlib.sha256(inventory).hexdigest(),
        inventory=inventory,
    )


def _tables(path: Path) -> Mapping[str, object] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast(Mapping[str, object], document) if isinstance(document, dict) else None


def _bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None
