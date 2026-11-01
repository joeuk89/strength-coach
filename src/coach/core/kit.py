"""The kit tables plate-pool generates, parsed into racks (ADR 0021, instance.md "Kit")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from coach.core.config import Dumbbells, Units
from coach.core.errors import Setup
from coach.core.rack import ListedRack, Position, RackRow

KIT_FORMATS = (1,)
SHORT_HASH_LENGTH = 8

type TablesState = Literal["current", "stale"]


@dataclass(frozen=True)
class KitRacks:
    plate_pool: str
    inventory_sha256: str
    racks: Mapping[str, ListedRack]

    @property
    def short_hash(self) -> str:
        return self.inventory_sha256[:SHORT_HASH_LENGTH]


@dataclass(frozen=True)
class KitFiles:
    """What `cli` read for one plate-pool location; `None` where a file is missing."""

    location: str
    kit: str
    tables: Mapping[str, object] | None
    inventory_sha256: str | None


def parse_kit_tables(
    document: Mapping[str, object], *, collars: str, dumbbells: Dumbbells, units: Units
) -> KitRacks:
    kit_format = document.get("format")
    if kit_format not in KIT_FORMATS:
        raise _unparseable(f"format {kit_format!r} is not one this engine parses {KIT_FORMATS}")
    tables = [_mapping(table, "tables[]") for table in _list(document.get("tables"), "tables")]
    applicable = [
        table
        for table in tables
        if table.get("collars", collars) == collars
        and table.get("pair", dumbbells == "pair") == (dumbbells == "pair")
    ]
    racks = {
        _text(table.get("implement"), "implement"): ListedRack(
            tuple(_row(row, units) for row in _list(table.get("rows"), "rows"))
        )
        for table in applicable
    }
    if "barbell" in {table.get("implement") for table in tables} and "barbell" not in racks:
        raise _unparseable(f"no barbell table has collars {collars!r}")
    return KitRacks(
        plate_pool=_text(document.get("plate_pool"), "plate_pool"),
        inventory_sha256=_text(document.get("inventory_sha256"), "inventory_sha256"),
        racks=racks,
    )


def tables_state(files: KitFiles) -> TablesState:
    if files.tables is None or files.inventory_sha256 is None:
        return "stale"
    return "current" if files.tables.get("inventory_sha256") == files.inventory_sha256 else "stale"


def require_current_tables(files: KitFiles) -> None:
    """The setup refusal every verb that rounds raises before it rounds (ADR 0021)."""
    if tables_state(files) == "stale":
        raise Setup(
            "kit_tables_stale",
            f"location {files.location}: kit/{files.kit}.achievable.json is missing or was not "
            f"built from kit/{files.kit}.json; run {generator_command(files.kit)}",
        )


def generator_command(kit: str) -> str:
    return f"npx plate-pool achievable --inventory kit/{kit}.json > kit/{kit}.achievable.json"


def _row(row: object, units: Units) -> RackRow:
    fields = _mapping(row, "rows[]")
    total = _mapping(fields.get("total"), "total")
    loading = _mapping(fields.get("loading"), "loading")
    positions = tuple(
        Position(
            _text(position.get("name"), "positions[].name"),
            tuple(_number(plate, "plates[]") for plate in _list(position.get("plates"), "plates")),
        )
        for position in (
            _mapping(item, "positions[]") for item in _list(loading.get("positions"), "positions")
        )
    )
    return RackRow(_number(total.get(units), f"total.{units}"), positions)


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _unparseable(f"{where} is not an object")
    return cast(Mapping[str, object], value)


def _list(value: object, where: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise _unparseable(f"{where} is not a list")
    return cast(list[object], value)


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise _unparseable(f"{where} is not a non-empty string")
    return value


def _number(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _unparseable(f"{where} is not a number")
    return value


def _unparseable(why: str) -> Setup:
    return Setup("kit_tables_stale", f"the kit tables {why}; regenerate them with plate-pool")
