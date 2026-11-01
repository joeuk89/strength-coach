import pytest

from coach.core.engine_pin import check_pin, generated_file_drift, notes_between
from coach.core.errors import Setup


def test_a_release_engine_matching_its_pin_raises_nothing() -> None:
    assert check_pin("1.2.0", "1.2.0") is None


def test_a_dev_engine_runs_against_any_release_pin_with_a_warning() -> None:
    warning = check_pin("1.3.0.dev0", "1.2.0")

    assert warning is not None
    assert warning.key == "engine_pin_dev@instance"
    assert warning.severity == "warning"
    assert warning.params == {"pinned_version": "1.2.0", "running_version": "1.3.0.dev0"}
    assert warning.rn is None
    assert "1.3.0.dev0" in warning.message
    assert "1.2.0" in warning.message


def test_a_release_engine_against_a_different_pin_stops() -> None:
    with pytest.raises(Setup) as raised:
        check_pin("1.3.0", "1.2.0")

    assert raised.value.code == "engine_pin_mismatch"
    assert "1.3.0" in raised.value.message
    assert "1.2.0" in raised.value.message


def test_upgrade_admits_a_release_engine_newer_than_the_pin() -> None:
    assert check_pin("1.10.0", "1.9.3", upgrading=True) is None
    assert check_pin("1.2.0", "1.2.0", upgrading=True) is None


def test_upgrade_refuses_a_release_engine_older_than_the_pin() -> None:
    with pytest.raises(Setup) as raised:
        check_pin("1.9.3", "1.10.0", upgrading=True)

    assert raised.value.code == "engine_pin_mismatch"
    assert "1.10.0" in raised.value.message


def test_upgrade_refuses_a_dev_engine_because_only_a_release_writes_the_pin() -> None:
    with pytest.raises(Setup) as raised:
        check_pin("1.3.0.dev0", "1.2.0", upgrading=True)

    assert raised.value.code == "engine_pin_required"


def test_migration_notes_are_those_of_each_major_crossed() -> None:
    notes = {2: "two", 3: "three", 4: "four"}

    assert notes_between("1.4.0", "3.0.1", notes) == ("two", "three")
    assert notes_between("3.0.0", "3.9.0", notes) == ()


def test_a_drifted_generated_file_is_a_warning_on_the_instance_naming_file_and_engine() -> None:
    flag = generated_file_drift("CLAUDE.md", "1.2.0")

    assert flag.key == "generated_file_drift@instance"
    assert flag.severity == "warning"
    assert flag.params == {"file": "CLAUDE.md", "engine_version": "1.2.0"}
    assert flag.rn is None
    assert flag.message.startswith("CLAUDE.md ")
