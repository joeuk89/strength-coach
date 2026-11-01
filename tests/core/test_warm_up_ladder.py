from coach.core.config import IncrementImplement
from coach.core.rack import ListedRack, Position, RackRow, grid_rack, warm_up_ladder


def a_row(load: float, *per_side: float) -> RackRow:
    return RackRow(load, (Position("left", per_side), Position("right", per_side)))


def loads(rows: tuple[RackRow, ...]) -> list[float]:
    return [row.load for row in rows]


def test_a_warm_up_takes_the_fewest_plates_inside_the_band_over_the_nearest_row() -> None:
    rack = ListedRack((a_row(80, 25, 5), a_row(85, 25, 5, 2.5), a_row(90, 25, 10)))

    assert loads(warm_up_ladder(rack, (88,))) == [80]


def test_a_warm_up_never_goes_above_its_target() -> None:
    rack = ListedRack((a_row(70, 25), a_row(75, 25, 2.5), a_row(80, 25, 5)))

    assert loads(warm_up_ladder(rack, (79,))) == [75]


def test_plate_count_ties_go_lighter() -> None:
    rack = ListedRack((a_row(75, 25, 2.5), a_row(80, 25, 5)))

    assert loads(warm_up_ladder(rack, (80,))) == [75]


def test_containment_beats_lighter_among_rows_with_the_fewest_plates() -> None:
    rack = ListedRack((a_row(40, 10), a_row(82.5, 30, 1.25), a_row(85, 22.5, 10)))

    assert loads(warm_up_ladder(rack, (40, 85))) == [40, 85]


def test_with_no_row_in_the_band_the_warm_up_takes_the_row_below_its_target() -> None:
    rack = ListedRack((a_row(20), a_row(70, 25)))

    assert loads(warm_up_ladder(rack, (60,))) == [20]


def test_a_warm_up_below_the_bare_implement_is_the_bare_implement() -> None:
    rack = ListedRack((a_row(20), a_row(70, 25)))

    assert loads(warm_up_ladder(rack, (15,))) == [20]


def test_at_a_grid_location_a_warm_up_rounds_to_the_row_no_heavier_than_its_target() -> None:
    rack = grid_rack(IncrementImplement(increment=2.5, base=20))

    assert loads(warm_up_ladder(rack, (62.5, 93.75))) == [62.5, 92.5]
