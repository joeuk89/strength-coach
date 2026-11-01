import copy
import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "kit"
KIT = "home"
INVENTORY = FIXTURES / f"{KIT}.json"
TABLES = FIXTURES / f"{KIT}.achievable.json"

_tables: dict[str, Any] = json.loads(TABLES.read_text(encoding="utf-8"))


def kit_tables() -> dict[str, Any]:
    return copy.deepcopy(_tables)
