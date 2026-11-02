from collections.abc import Collection, Mapping, Sequence

from coach.core.config import Config, Location, PlatePoolLocation, Units
from coach.core.kit import (
    KitFiles,
    location_racks,
    parse_kit_tables,
    require_current_tables,
    tables_state,
)
from coach.core.rack import Rack


def racks_by_location(
    config: Config, kits: Sequence[KitFiles], named: Collection[str]
) -> dict[str, Mapping[str, Rack]]:
    """Each location's racks; a plate-pool location in `named` must have current tables."""
    return _racks(config.locations, kits, named, config.athlete.units)


def current_racks(
    locations: Sequence[Location], kits: Sequence[KitFiles], units: Units
) -> dict[str, Mapping[str, Rack]]:
    """Each location's racks, with none at a plate-pool location whose tables are stale."""
    current = {kit.location for kit in kits if tables_state(kit) == "current"}
    return _racks(locations, kits, current, units)


def _racks(
    locations: Sequence[Location], kits: Sequence[KitFiles], named: Collection[str], units: Units
) -> dict[str, Mapping[str, Rack]]:
    files = {kit.location: kit for kit in kits}
    racks: dict[str, Mapping[str, Rack]] = {}
    for location in locations:
        kit = None
        if isinstance(location, PlatePoolLocation) and location.name in named:
            tables = files.get(location.name) or KitFiles(location.name, location.kit, None, None)
            require_current_tables(tables)
            assert tables.tables is not None
            kit = parse_kit_tables(tables.tables, choices=location.choices(), units=units)
        racks[location.name] = location_racks(location, kit)
    return racks
