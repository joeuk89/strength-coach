import pytest

from coach.core.engine_pin import check_pin
from coach.core.errors import Setup


def test_a_release_engine_matching_its_pin_raises_nothing() -> None:
    assert check_pin("1.2.0", "1.2.0") is None


def test_a_dev_engine_runs_against_any_release_pin_with_a_warning() -> None:
    notice = check_pin("1.3.0.dev0", "1.2.0")

    assert notice is not None
    assert notice.code == "engine_pin_dev"
    assert "1.3.0.dev0" in notice.message
    assert "1.2.0" in notice.message


def test_a_release_engine_against_a_different_pin_stops() -> None:
    with pytest.raises(Setup) as raised:
        check_pin("1.3.0", "1.2.0")

    assert raised.value.code == "engine_pin_mismatch"
    assert "1.3.0" in raised.value.message
    assert "1.2.0" in raised.value.message
