"""The kit tables plate-pool generates, parsed into racks (ADR 0021, instance.md "Kit")."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from coach.core.config import GridLocation, ImplementChoice, Location, Units
from coach.core.errors import Setup
from coach.core.rack import PRECISION, ListedRack, Position, Rack, RackRow, grid_rack

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
    inventory: bytes | None = None


def parse_kit_tables(
    document: Mapping[str, object], *, choices: Mapping[str, ImplementChoice], units: Units
) -> KitRacks:
    """The rack of each implement in `choices`: the rows of the tables its choice selects, one
    row per total, the table of the hardware id listed first winning a total two tables build."""
    kit_format = document.get("format")
    if kit_format not in KIT_FORMATS:
        raise _unparseable(f"format {kit_format!r} is not one this engine parses {KIT_FORMATS}")
    tables = [_mapping(table, "tables[]") for table in _list(document.get("tables"), "tables")]
    racks: dict[str, ListedRack] = {}
    for implement, choice in choices.items():
        offered = [table for table in tables if table.get("implement") == implement]
        if offered:
            rows: dict[float, RackRow] = {}
            for hardware, table in _chosen(implement, offered, choice):
                for row in _list(table.get("rows"), "rows"):
                    parsed = _row(row, units, hardware)
                    rows.setdefault(round(parsed.load, PRECISION), parsed)
            racks[implement] = ListedRack(tuple(rows.values()))
    return KitRacks(
        plate_pool=_text(document.get("plate_pool"), "plate_pool"),
        inventory_sha256=_text(document.get("inventory_sha256"), "inventory_sha256"),
        racks=racks,
    )


def _chosen(
    implement: str, offered: Sequence[Mapping[str, object]], choice: ImplementChoice
) -> list[tuple[str | None, Mapping[str, object]]]:
    hardware = list(
        dict.fromkeys(_text(t["hardware"], "tables[].hardware") for t in offered if "hardware" in t)
    )
    ids = _chosen_hardware(implement, hardware, choice)
    pairs = any("pair" in t for t in offered)
    if not pairs and choice.single:
        raise _unmatched(f"offer {implement} no pair or single, and the location names single")
    chosen: list[tuple[str | None, Mapping[str, object]]] = []
    for hardware_id in ids:
        matching = [
            t
            for t in offered
            if t.get("hardware") == hardware_id
            and (not pairs or t.get("pair") == (not choice.single))
        ]
        if len(matching) != 1:
            raise _unparseable(f"hold {len(matching)} {implement} tables for one choice, not 1")
        chosen.append((hardware_id, matching[0]))
    return chosen


def _chosen_hardware(
    implement: str, hardware: Sequence[str], choice: ImplementChoice
) -> tuple[str | None, ...]:
    """The hardware ids whose tables `choice` selects, `(None,)` where the tables carry none."""
    ids = choice.hardware_ids
    named = "no hardware" if choice.hardware is None else ", ".join(ids) or "an empty list"
    if not hardware:
        if choice.hardware is not None:
            raise _unmatched(f"offer {implement} no hardware, and the location names {named}")
        return (None,)
    offer = f"offer {implement} hardware {', '.join(hardware)}"
    if not ids:
        raise _unmatched(f"{offer}, and the location names {named}")
    unknown = next((i for i in ids if i not in hardware), None)
    if unknown is not None:
        raise _unmatched(f"{offer}, and the location names {unknown}")
    repeated = next((i for i in ids if ids.count(i) > 1), None)
    if repeated is not None:
        raise _unmatched(f"{offer}, and the location names {repeated} twice")
    return ids


def location_racks(location: Location, kit: KitRacks | None) -> dict[str, Rack]:
    """The rack of each equipment kind the location's `implements` maps (instance.md)."""
    if isinstance(location, GridLocation):
        return {
            kind: grid_rack(location.implement[name]) for kind, name in location.implements.items()
        }
    if kit is None:
        return {}
    return {
        kind: kit.racks[name] for kind, name in location.implements.items() if name in kit.racks
    }


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


def _row(row: object, units: Units, hardware: str | None) -> RackRow:
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
    return RackRow(_number(total.get(units), f"total.{units}"), positions, hardware)


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


def _unmatched(why: str) -> Setup:
    return Setup(
        "kit_tables_stale",
        f"the kit tables {why}; name one on offer in the location's implement table or "
        "regenerate the tables with plate-pool",
    )


def _unparseable(why: str) -> Setup:
    return Setup("kit_tables_stale", f"the kit tables {why}; regenerate them with plate-pool")
