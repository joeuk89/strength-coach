from typing import get_args

from coach.core.config import IncrementImplement, RackImplement
from coach.core.load import Load, LoadMode
from coach.core.rack import Rounded, grid_rack, next_row_down, next_row_up, round_to_rack
from coach.core.registries.program import LOAD_MODES

BAR = grid_rack(IncrementImplement(increment=5, base=20, max=100))
DUMBBELLS = grid_rack(RackImplement(rack=(10, 15, 20, 22.5, 25, 30)))
ASSISTANCE = grid_rack(RackImplement(rack=(0, 10, 20, 30, 40)))


def test_a_step_up_rounds_to_the_nearest_row() -> None:
    assert round_to_rack(BAR, Load(63, "total"), "step_up") == Rounded(Load(65, "total"), "row")
    assert round_to_rack(BAR, Load(61, "total"), "step_up") == Rounded(Load(60, "total"), "row")


def test_a_step_up_halfway_between_rows_takes_the_lighter() -> None:
    assert round_to_rack(BAR, Load(62.5, "total"), "step_up").load == Load(60, "total")


def test_a_cut_rounds_to_the_nearest_row_no_heavier() -> None:
    assert round_to_rack(BAR, Load(64.9, "total"), "cut") == Rounded(Load(60, "total"), "row")


def test_a_hold_rounds_no_heavier() -> None:
    assert round_to_rack(BAR, Load(69, "total"), "hold").load == Load(65, "total")


def test_a_load_on_a_row_stays_on_it() -> None:
    for rounding in ("step_up", "cut", "hold"):
        assert round_to_rack(BAR, Load(70, "total"), rounding).load == Load(70, "total")


def test_assistance_rounds_the_other_way_so_a_cut_never_takes_assistance_away() -> None:
    assert round_to_rack(ASSISTANCE, Load(23, "assisted"), "cut").load == Load(30, "assisted")
    assert round_to_rack(ASSISTANCE, Load(23, "assisted"), "hold").load == Load(30, "assisted")
    assert round_to_rack(ASSISTANCE, Load(23, "assisted"), "step_up").load == Load(20, "assisted")


def test_a_per_hand_load_rounds_per_hand_and_doubles_for_the_total() -> None:
    rounded = round_to_rack(DUMBBELLS, Load(24, "per_hand_x2"), "cut")

    assert rounded.load == Load(22.5, "per_hand_x2")
    assert rounded.load.total == 45


def test_a_single_implement_load_rounds_as_one_implement_and_is_its_own_total() -> None:
    rounded = round_to_rack(DUMBBELLS, Load(24, "single_implement"), "step_up")

    assert rounded.load == Load(25, "single_implement")
    assert rounded.load.total == 25


def test_a_target_above_the_top_row_rounds_to_the_top_with_rack_top() -> None:
    assert round_to_rack(BAR, Load(140, "total"), "step_up") == Rounded(
        Load(100, "total"), "rack_top"
    )
    assert round_to_rack(BAR, Load(140, "total"), "cut") == Rounded(Load(100, "total"), "rack_top")


def test_a_target_below_the_bottom_row_rounds_to_the_bare_implement() -> None:
    assert round_to_rack(BAR, Load(12, "total"), "cut").load == Load(20, "total")


def test_the_next_row_up_is_one_row_heavier() -> None:
    assert next_row_up(DUMBBELLS, Load(20, "per_hand_x2")) == Rounded(
        Load(22.5, "per_hand_x2"), "row"
    )


def test_at_the_top_of_the_rack_the_next_row_up_holds_with_rack_top() -> None:
    assert next_row_up(DUMBBELLS, Load(30, "per_hand_x2")) == Rounded(
        Load(30, "per_hand_x2"), "rack_top"
    )


def test_the_next_row_down_is_one_row_lighter_and_none_at_the_bottom() -> None:
    assert next_row_down(DUMBBELLS, Load(22.5, "per_hand_x2")) == Load(20, "per_hand_x2")
    assert next_row_down(DUMBBELLS, Load(10, "per_hand_x2")) is None


def test_load_modes_are_the_load_mode_registry() -> None:
    assert get_args(LoadMode.__value__) == LOAD_MODES.names()
