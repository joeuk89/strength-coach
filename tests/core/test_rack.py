from collections.abc import Iterable

from coach.core.config import IncrementImplement, RackImplement
from coach.core.rack import RackRow, grid_rack


def loads_of(rows: Iterable[RackRow]) -> list[float]:
    return [row.load for row in rows]


def test_an_increment_implement_with_base_and_max_yields_every_multiple_between_them() -> None:
    rack = grid_rack(IncrementImplement(increment=2.5, base=20, max=180))

    rows = loads_of(rack.rows_within(0, 1000))

    assert rows == [20 + 2.5 * step for step in range(65)]
    assert rows[0] == 20
    assert rows[-1] == 180
    assert rack.top is not None and rack.top.load == 180


def test_an_increment_implement_without_max_is_unbounded_above() -> None:
    rack = grid_rack(IncrementImplement(increment=2.5, base=20))

    assert rack.top is None
    assert loads_of(rack.rows_within(9995, 10_000)) == [9995, 9997.5, 10_000]
    above = rack.row_above(1_000_000)
    assert above is not None and above.load == 1_000_002.5


def test_an_increment_implement_without_base_starts_at_zero() -> None:
    rack = grid_rack(IncrementImplement(increment=5))

    assert loads_of(rack.rows_within(0, 12)) == [0, 5, 10]


def test_a_listed_rack_yields_its_rows_in_order() -> None:
    rack = grid_rack(RackImplement(rack=(10, 4, 6, 8)))

    assert loads_of(rack.rows_within(0, 100)) == [4, 6, 8, 10]
    assert rack.top is not None and rack.top.load == 10
    assert rack.bottom.load == 4


def test_the_row_below_a_load_over_the_top_is_the_top_row() -> None:
    rack = grid_rack(IncrementImplement(increment=2.5, base=20, max=180))

    below = rack.row_below(500)
    assert below is not None and below.load == 180
    assert rack.row_above(180) is None
    assert rack.row_below(20) is None
