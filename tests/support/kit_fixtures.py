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


SPLIT_STANDARD_PAIR = (7.5, 10, 70, 75, 80)
SPLIT_LONG_PAIR = (67.5, 70, 75, 80, 100, 120)
SPLIT_BARE_PAIR = (5,)
SPLIT_STANDARD_SINGLE = (10, 40)
SPLIT_LONG_SINGLE = (35, 40, 60)


def split_hardware_tables() -> dict[str, Any]:
    """A dumbbell whose two screws build overlapping parts of its range, as the pair and single
    tables plate-pool emits per hardware id, beside a leg attachment with no hardware."""
    tables = [
        _table("dumbbell", "screw-standard", True, SPLIT_STANDARD_PAIR),
        _table("dumbbell", "screw-long", True, SPLIT_LONG_PAIR),
        _table("dumbbell", "none", True, SPLIT_BARE_PAIR),
        _table("dumbbell", "screw-standard", False, SPLIT_STANDARD_SINGLE),
        _table("dumbbell", "screw-long", False, SPLIT_LONG_SINGLE),
        _table("dumbbell", "none", False, SPLIT_BARE_PAIR),
        _table("leg", None, None, (2.5, 5)),
    ]
    return {
        "format": 1,
        "plate_pool": "1.0.1",
        "inventory_sha256": "0" * 64,
        "name": "Split screws",
        "tables": tables,
    }


def _table(
    implement: str, hardware: str | None, pair: bool | None, totals: tuple[float, ...]
) -> dict[str, Any]:
    table: dict[str, Any] = {"implement": implement}
    if hardware is not None:
        table["hardware"] = hardware
    if pair is not None:
        table["pair"] = pair
    table["rows"] = [
        {
            "total": {"lb": total, "kg": round(total * 0.45359237, 1)},
            "loading": {"positions": [{"name": "a", "plates": [], "ids": []}]},
        }
        for total in totals
    ]
    return table
