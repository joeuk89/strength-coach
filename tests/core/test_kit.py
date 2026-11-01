from itertools import pairwise

import pytest
from support.kit_fixtures import kit_tables

from coach.core.config import GridLocation, IncrementImplement, PlatePoolLocation, RackImplement
from coach.core.errors import Setup
from coach.core.kit import (
    KitFiles,
    location_racks,
    parse_kit_tables,
    require_current_tables,
    tables_state,
)
from coach.core.load import Load
from coach.core.rack import Position, RackRow, round_to_rack, warm_up_ladder


def test_the_parser_builds_a_rack_per_implement_from_the_kit_fixture() -> None:
    kit = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="pair", units="lb")

    assert set(kit.racks) == {"barbell", "dumbbell", "kettlebell", "leg", "vest"}
    barbell = kit.racks["barbell"]
    assert barbell.bottom == RackRow(20, (Position("left", ()), Position("right", ())))
    assert barbell.top is not None and barbell.top.load == 190
    assert [row.load for row in barbell.rows_within(110, 125)] == [110, 115, 120, 125]
    assert barbell.rows_within(120, 120)[0].positions == (
        Position("left", (25, 25)),
        Position("right", (25, 25)),
    )


def test_the_location_collars_choose_the_barbell_table() -> None:
    kit = parse_kit_tables(kit_tables(), collars="spinlock", dumbbells="pair", units="lb")

    assert kit.racks["barbell"].bottom.load == 22.5


def test_the_location_dumbbells_choose_the_pair_or_single_table() -> None:
    pair = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="pair", units="lb")
    single = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="single", units="lb")

    assert pair.racks["dumbbell"].top == RackRow(
        45, (Position("end-a", (10, 5, 2.5)), Position("end-b", (10, 5, 2.5)))
    )
    single_top = single.racks["dumbbell"].top
    assert single_top is not None and single_top.load == 180


def test_rows_are_read_in_the_athletes_units() -> None:
    kit = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="pair", units="kg")

    assert kit.racks["barbell"].bottom.load == 9.1
    assert [row.load for row in kit.racks["vest"].rows_within(0, 100)] == [2, 4, 6]


def test_the_header_carries_the_generator_version_and_the_inventory_hash() -> None:
    document = kit_tables()

    kit = parse_kit_tables(document, collars="clamp", dumbbells="pair", units="lb")

    assert kit.plate_pool == "0.3.0"
    assert kit.inventory_sha256 == document["inventory_sha256"]
    assert kit.short_hash == document["inventory_sha256"][:8]


def test_an_unknown_format_is_refused() -> None:
    document = kit_tables()
    document["format"] = 2

    with pytest.raises(Setup) as raised:
        parse_kit_tables(document, collars="clamp", dumbbells="pair", units="lb")

    assert raised.value.code == "kit_tables_stale"
    assert "format 2" in raised.value.message


def test_a_collar_choice_with_no_table_is_refused() -> None:
    with pytest.raises(Setup) as raised:
        parse_kit_tables(kit_tables(), collars="magnetic", dumbbells="pair", units="lb")

    assert "magnetic" in raised.value.message


def test_a_rounded_fixture_load_is_a_row_the_kit_can_build() -> None:
    kit = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="pair", units="lb")

    assert round_to_rack(kit.racks["barbell"], Load(118, "total"), "cut").load == Load(115, "total")
    assert round_to_rack(kit.racks["dumbbell"], Load(33, "per_hand_x2"), "step_up").load == Load(
        35, "per_hand_x2"
    )


def test_a_warm_up_ladder_on_the_fixture_barbell_never_strips_a_plate() -> None:
    barbell = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="pair", units="lb").racks[
        "barbell"
    ]

    ladder = warm_up_ladder(barbell, (30, 81, 135))

    assert [row.load for row in ladder] == [30, 80, 130]
    assert all(later.keeps_plates_of(earlier) for earlier, later in pairwise(ladder))


def a_kit(*, tables_hash: str | None = "abc", inventory_sha256: str | None = "abc") -> KitFiles:
    tables = None if tables_hash is None else {"format": 1, "inventory_sha256": tables_hash}
    return KitFiles("home", "home", tables, inventory_sha256)


def test_tables_built_from_the_inventory_are_current() -> None:
    assert tables_state(a_kit()) == "current"
    require_current_tables(a_kit())


@pytest.mark.parametrize(
    "kit",
    [
        a_kit(tables_hash="abc", inventory_sha256="def"),
        a_kit(tables_hash=None),
        a_kit(inventory_sha256=None),
    ],
    ids=["hash differs", "tables missing", "inventory missing"],
)
def test_tables_not_built_from_the_inventory_are_stale(kit: KitFiles) -> None:
    assert tables_state(kit) == "stale"


def test_stale_tables_refuse_naming_the_location_and_the_generator_command() -> None:
    with pytest.raises(Setup) as raised:
        require_current_tables(a_kit(inventory_sha256="def"))

    assert raised.value.code == "kit_tables_stale"
    assert "location home" in raised.value.message
    assert "npx plate-pool achievable --inventory kit/home.json" in raised.value.message


def test_a_plate_pool_location_supplies_the_kit_rack_of_each_implement_it_maps() -> None:
    location = PlatePoolLocation(
        "home", kit="home", collars="clamp", dumbbells="pair", implements={"barbell": "barbell"}
    )
    kit = parse_kit_tables(kit_tables(), collars="clamp", dumbbells="pair", units="lb")

    racks = location_racks(location, kit)

    assert set(racks) == {"barbell"}
    assert racks["barbell"].rows_within(120, 120)


def test_a_grid_location_supplies_the_rack_of_each_implement_table() -> None:
    location = GridLocation(
        "gym",
        implements={"barbell": "bar", "machine": "stack"},
        implement={"bar": IncrementImplement(2.5, base=20), "stack": RackImplement((5, 10))},
    )

    racks = location_racks(location, None)

    assert racks["barbell"].rows_within(22.5, 22.5)
    assert racks["machine"].top == RackRow(10)


def test_a_plate_pool_location_without_its_kit_supplies_nothing() -> None:
    location = PlatePoolLocation(
        "home", kit="home", collars="clamp", dumbbells="pair", implements={"barbell": "barbell"}
    )

    assert location_racks(location, None) == {}
