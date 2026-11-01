from collections.abc import Collection, Mapping, Sequence

from coach.core.config import Config, PlatePoolLocation
from coach.core.kit import KitFiles, location_racks, parse_kit_tables, require_current_tables
from coach.core.rack import Rack


def racks_by_location(
    config: Config, kits: Sequence[KitFiles], named: Collection[str]
) -> dict[str, Mapping[str, Rack]]:
    """Each location's racks; a plate-pool location in `named` must have current tables."""
    files = {kit.location: kit for kit in kits}
    racks: dict[str, Mapping[str, Rack]] = {}
    for location in config.locations:
        kit = None
        if isinstance(location, PlatePoolLocation) and location.name in named:
            tables = files.get(location.name) or KitFiles(location.name, location.kit, None, None)
            require_current_tables(tables)
            assert tables.tables is not None
            kit = parse_kit_tables(
                tables.tables,
                collars=location.collars,
                dumbbells=location.dumbbells,
                units=config.athlete.units,
            )
        racks[location.name] = location_racks(location, kit)
    return racks
