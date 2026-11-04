from itertools import pairwise

import pytest
from support.kit_fixtures import (
    SPLIT_BARE_PAIR,
    SPLIT_LONG_PAIR,
    SPLIT_STANDARD_PAIR,
    kit_tables,
    split_hardware_tables,
)

from coach.core.config import (
    GridLocation,
    ImplementChoice,
    IncrementImplement,
    PlatePoolLocation,
    RackImplement,
)
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

CLAMP = ImplementChoice(hardware="collar-clamp")
STANDARD_PAIR = ImplementChoice(hardware="screw-standard")
HOME = {
    "barbell": CLAMP,
    "dumbbell": STANDARD_PAIR,
    "kettlebell": ImplementChoice(hardware="none"),
    "leg": ImplementChoice(),
    "vest": ImplementChoice(),
}


def stale(choices: dict[str, ImplementChoice]) -> Setup:
    with pytest.raises(Setup) as raised:
        parse_kit_tables(kit_tables(), choices=choices, units="lb")
    assert raised.value.code == "kit_tables_stale"
    return raised.value


def test_the_parser_builds_a_rack_per_implement_from_the_kit_fixture() -> None:
    kit = parse_kit_tables(kit_tables(), choices=HOME, units="lb")

    assert set(kit.racks) == {"barbell", "dumbbell", "kettlebell", "leg", "vest"}
    barbell = kit.racks["barbell"]
    assert barbell.bottom == RackRow(
        20, (Position("left", ()), Position("right", ())), "collar-clamp"
    )
    assert barbell.top is not None and barbell.top.load == 190
    assert [row.load for row in barbell.rows_within(110, 125)] == [110, 115, 120, 125]
    assert barbell.rows_within(120, 120)[0].positions == (
        Position("left", (25, 25)),
        Position("right", (25, 25)),
    )


def test_the_barbell_hardware_choice_chooses_the_barbell_table() -> None:
    choices = HOME | {"barbell": ImplementChoice(hardware="collar-spinlock")}

    kit = parse_kit_tables(kit_tables(), choices=choices, units="lb")

    assert kit.racks["barbell"].bottom.load == 22.5


def test_the_dumbbell_single_choice_chooses_the_pair_or_single_table() -> None:
    single = HOME | {"dumbbell": ImplementChoice(hardware="screw-standard", single=True)}

    pair = parse_kit_tables(kit_tables(), choices=HOME, units="lb")
    one = parse_kit_tables(kit_tables(), choices=single, units="lb")

    assert pair.racks["dumbbell"].top == RackRow(
        45, (Position("a", (10, 5, 2.5)), Position("b", (10, 5, 2.5))), "screw-standard"
    )
    single_top = one.racks["dumbbell"].top
    assert single_top is not None and single_top.load == 180


def test_the_dumbbell_hardware_choice_chooses_the_dumbbell_table() -> None:
    bare = HOME | {"dumbbell": ImplementChoice(hardware="none")}

    kit = parse_kit_tables(kit_tables(), choices=bare, units="lb")

    assert kit.racks["dumbbell"].bottom == RackRow(
        5, (Position("a", ()), Position("b", ())), "none"
    )
    assert kit.racks["dumbbell"].top == RackRow(
        40, (Position("a", (10, 5, 2.5)), Position("b", (10, 5, 2.5))), "none"
    )


def test_an_implement_whose_tables_carry_no_hardware_needs_no_choice() -> None:
    kit = parse_kit_tables(kit_tables(), choices={"leg": ImplementChoice()}, units="lb")

    assert set(kit.racks) == {"leg"}
    assert kit.racks["leg"].bottom.load == 2.5


def test_an_implement_the_location_does_not_name_gets_no_rack_and_needs_no_choice() -> None:
    kit = parse_kit_tables(kit_tables(), choices={"barbell": CLAMP}, units="lb")

    assert set(kit.racks) == {"barbell"}


def test_a_hardware_id_no_table_has_is_refused_naming_the_ids_on_offer() -> None:
    error = stale(HOME | {"barbell": ImplementChoice(hardware="collar-magnetic")})

    assert "barbell" in error.message
    assert "collar-magnetic" in error.message
    assert "collar-clamp, collar-spinlock, none" in error.message


def test_no_hardware_choice_where_the_tables_carry_hardware_is_refused() -> None:
    error = stale(HOME | {"dumbbell": ImplementChoice()})

    assert "dumbbell" in error.message
    assert "screw-standard, screw-long, none" in error.message


def test_a_hardware_choice_where_the_tables_carry_none_is_refused() -> None:
    error = stale(HOME | {"leg": ImplementChoice(hardware="none")})

    assert "leg" in error.message
    assert "no hardware" in error.message


def test_single_where_the_tables_carry_no_pair_is_refused() -> None:
    error = stale(HOME | {"barbell": ImplementChoice(hardware="collar-clamp", single=True)})

    assert "barbell" in error.message
    assert "single" in error.message


def split(hardware: str | tuple[str, ...] | None, *, single: bool = False) -> list[RackRow]:
    choice = ImplementChoice(hardware=hardware, single=single)
    kit = parse_kit_tables(split_hardware_tables(), choices={"dumbbell": choice}, units="lb")
    return list(kit.racks["dumbbell"].rows)


def split_refusal(implement: str, hardware: tuple[str, ...]) -> Setup:
    with pytest.raises(Setup) as raised:
        parse_kit_tables(
            split_hardware_tables(),
            choices={implement: ImplementChoice(hardware=hardware)},
            units="lb",
        )
    assert raised.value.code == "kit_tables_stale"
    assert implement in raised.value.message
    return raised.value


def test_a_hardware_list_reads_the_union_of_its_tables_with_the_first_id_winning_a_shared_total() -> (
    None
):
    rows = split(("screw-standard", "screw-long"))

    assert [(row.load, row.hardware) for row in rows] == [
        (7.5, "screw-standard"),
        (10, "screw-standard"),
        (67.5, "screw-long"),
        (70, "screw-standard"),
        (75, "screw-standard"),
        (80, "screw-standard"),
        (100, "screw-long"),
        (120, "screw-long"),
    ]


def test_a_hardware_list_in_the_other_order_gives_the_shared_totals_to_the_other_id() -> None:
    rows = split(("screw-long", "screw-standard"))

    assert [(row.load, row.hardware) for row in rows if row.load in (70, 75, 80)] == [
        (70, "screw-long"),
        (75, "screw-long"),
        (80, "screw-long"),
    ]
    assert [row.load for row in rows] == [7.5, 10, 67.5, 70, 75, 80, 100, 120]


def test_none_in_a_hardware_list_adds_the_bare_handle_rows() -> None:
    rows = split(("screw-standard", "screw-long", "none"))

    assert (rows[0].load, rows[0].hardware) == (5, "none")
    assert len(rows) == 9


def test_a_hardware_string_reads_its_one_table_as_before() -> None:
    rows = split("screw-standard")

    assert [row.load for row in rows] == list(SPLIT_STANDARD_PAIR)
    assert {row.hardware for row in rows} == {"screw-standard"}
    assert [row.load for row in split("none")] == list(SPLIT_BARE_PAIR)
    assert [row.load for row in split("screw-long")] == list(SPLIT_LONG_PAIR)


def test_single_with_a_hardware_list_reads_the_single_table_of_each_id() -> None:
    rows = split(("screw-standard", "screw-long"), single=True)

    assert [(row.load, row.hardware) for row in rows] == [
        (10, "screw-standard"),
        (35, "screw-long"),
        (40, "screw-standard"),
        (60, "screw-long"),
    ]


def test_the_rows_of_an_implement_with_no_hardware_carry_none() -> None:
    kit = parse_kit_tables(split_hardware_tables(), choices={"leg": ImplementChoice()}, units="lb")

    assert {row.hardware for row in kit.racks["leg"].rows} == {None}


def test_a_hardware_list_naming_an_id_no_table_has_is_refused_naming_the_ids_on_offer() -> None:
    error = split_refusal("dumbbell", ("screw-standard", "screw-magnetic"))

    assert "screw-magnetic" in error.message
    assert "screw-standard, screw-long, none" in error.message


def test_a_hardware_list_where_the_tables_carry_no_hardware_is_refused() -> None:
    error = split_refusal("leg", ("none",))

    assert "no hardware" in error.message


def test_an_empty_hardware_list_is_refused_naming_the_ids_on_offer() -> None:
    error = split_refusal("dumbbell", ())

    assert "empty" in error.message
    assert "screw-standard, screw-long, none" in error.message


def test_a_hardware_list_naming_an_id_twice_is_refused_naming_the_ids_on_offer() -> None:
    error = split_refusal("dumbbell", ("screw-long", "screw-standard", "screw-long"))

    assert "screw-long twice" in error.message
    assert "screw-standard, screw-long, none" in error.message


def test_rows_are_read_in_the_athletes_units() -> None:
    kit = parse_kit_tables(kit_tables(), choices=HOME, units="kg")

    assert kit.racks["barbell"].bottom.load == 9.1
    assert [row.load for row in kit.racks["vest"].rows_within(0, 100)] == [2, 4, 6]


def test_the_header_carries_the_generator_version_and_the_inventory_hash() -> None:
    document = kit_tables()

    kit = parse_kit_tables(document, choices=HOME, units="lb")

    assert kit.plate_pool == "0.3.0"
    assert kit.inventory_sha256 == document["inventory_sha256"]
    assert kit.short_hash == document["inventory_sha256"][:8]


def test_an_unknown_format_is_refused() -> None:
    document = kit_tables()
    document["format"] = 2

    with pytest.raises(Setup) as raised:
        parse_kit_tables(document, choices=HOME, units="lb")

    assert raised.value.code == "kit_tables_stale"
    assert "format 2" in raised.value.message


def test_a_rounded_fixture_load_is_a_row_the_kit_can_build() -> None:
    kit = parse_kit_tables(kit_tables(), choices=HOME, units="lb")

    assert round_to_rack(kit.racks["barbell"], Load(118, "total"), "cut").load == Load(115, "total")
    assert round_to_rack(kit.racks["dumbbell"], Load(33, "per_hand_x2"), "step_up").load == Load(
        35, "per_hand_x2"
    )


def test_a_warm_up_ladder_on_the_fixture_barbell_never_strips_a_plate() -> None:
    barbell = parse_kit_tables(kit_tables(), choices=HOME, units="lb").racks["barbell"]

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
        "home", kit="home", implements={"barbell": "barbell"}, implement={"barbell": CLAMP}
    )
    kit = parse_kit_tables(kit_tables(), choices=HOME, units="lb")

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
        "home", kit="home", implements={"barbell": "barbell"}, implement={"barbell": CLAMP}
    )

    assert location_racks(location, None) == {}
