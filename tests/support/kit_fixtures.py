import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from coach.core.kit import KitFiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kit"
KIT = "home"
INVENTORY = FIXTURES / f"{KIT}.json"
TABLES = FIXTURES / f"{KIT}.achievable.json"

_tables: dict[str, Any] = json.loads(TABLES.read_text(encoding="utf-8"))


def kit_tables() -> dict[str, Any]:
    return copy.deepcopy(_tables)


def kit_files(location: str = "home", **tables: Any) -> KitFiles:
    """The fixture kit as `cli` reads it: the tables document, the inventory's hash and its
    bytes."""
    document = kit_tables() | tables
    inventory = INVENTORY.read_bytes()
    return KitFiles(location, KIT, document, hashlib.sha256(inventory).hexdigest(), inventory)
