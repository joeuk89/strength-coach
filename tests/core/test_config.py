import copy
from typing import Any

import pytest

from coach.core.config import (
    Athlete,
    Config,
    Engine,
    GridLocation,
    Hevy,
    IncrementImplement,
    PlatePoolLocation,
    RackImplement,
    parse_config,
)
from coach.core.errors import Setup

ATHLETE: dict[str, Any] = {
    "units": "kg",
    "bodyweight_units": "lb",
    "week_starts": "monday",
    "timezone": "Europe/London",
    "available_days": ["monday", "wednesday", "friday"],
    "session_minutes": 60,
    "checkin_cadence_days": 14,
}

DOCUMENT: dict[str, Any] = {
    "engine": {"version": "0.3.0"},
    "athlete": ATHLETE,
    "hevy": {},
    "location": {
        "home": {
            "kind": "plate-pool",
            "kit": "home",
            "collars": "clamp",
            "dumbbells": "pair",
            "implements": {"barbell": "barbell", "dumbbell": "dumbbell"},
        },
        "gym": {
            "kind": "grid",
            "implements": {"barbell": "bar", "dumbbell": "rack", "machine": "stack"},
            "implement": {
                "bar": {"increment": 2.5, "base": 20, "max": 180},
                "rack": {"rack": [4, 6, 8, 12.5]},
                "stack": {"increment": 5},
            },
        },
    },
}


def a_document(**changes: Any) -> dict[str, Any]:
    document = copy.deepcopy(DOCUMENT)
    document.update(changes)
    return document


def refusal(document: dict[str, Any]) -> Setup:
    with pytest.raises(Setup) as raised:
        parse_config(document)
    assert raised.value.code == "config_unknown_key"
    return raised.value


def test_a_whole_coach_toml_parses_into_a_typed_config() -> None:
    assert parse_config(DOCUMENT) == Config(
        engine=Engine(version="0.3.0"),
        athlete=Athlete(
            units="kg",
            bodyweight_units="lb",
            week_starts="monday",
            timezone="Europe/London",
            available_days=("monday", "wednesday", "friday"),
            session_minutes=60,
            checkin_cadence_days=14,
        ),
        hevy=Hevy(),
        locations=(
            PlatePoolLocation(
                name="home",
                kit="home",
                collars="clamp",
                dumbbells="pair",
                implements={"barbell": "barbell", "dumbbell": "dumbbell"},
            ),
            GridLocation(
                name="gym",
                implements={"barbell": "bar", "dumbbell": "rack", "machine": "stack"},
                implement={
                    "bar": IncrementImplement(increment=2.5, base=20, max=180),
                    "rack": RackImplement(rack=(4, 6, 8, 12.5)),
                    "stack": IncrementImplement(increment=5),
                },
            ),
        ),
    )


def test_hevy_is_off_without_the_table_and_locations_are_optional() -> None:
    document = a_document()
    del document["hevy"]
    del document["location"]

    config = parse_config(document)

    assert config.hevy is None
    assert config.locations == ()


def test_the_checkin_cadence_defaults_to_seven_days() -> None:
    document = a_document()
    del document["athlete"]["checkin_cadence_days"]

    assert parse_config(document).athlete.checkin_cadence_days == 7


def test_an_unknown_table_is_refused_naming_it() -> None:
    error = refusal(a_document(caps={"squat": 100}))

    assert "caps" in error.message


@pytest.mark.parametrize(
    ("table", "key"),
    [("engine", "channel"), ("athlete", "experience"), ("hevy", "enabled")],
)
def test_an_unknown_key_is_refused_naming_it(table: str, key: str) -> None:
    document = a_document()
    document[table][key] = "x"

    error = refusal(document)

    assert f"{table}.{key}" in error.message


@pytest.mark.parametrize(
    ("location", "key"),
    [("home", "url"), ("gym", "kit")],
)
def test_an_unknown_location_key_is_refused_naming_it(location: str, key: str) -> None:
    document = a_document()
    document["location"][location][key] = "x"

    error = refusal(document)

    assert f"location.{location}.{key}" in error.message


def test_an_unknown_grid_implement_key_is_refused_naming_it() -> None:
    document = a_document()
    document["location"]["gym"]["implement"]["bar"]["step"] = 1

    error = refusal(document)

    assert "location.gym.implement.bar.step" in error.message


def test_an_implements_key_outside_the_equipment_kinds_is_refused() -> None:
    document = a_document()
    document["location"]["gym"]["implements"]["trap_bar"] = "bar"

    error = refusal(document)

    assert "location.gym.implements.trap_bar" in error.message


def test_a_grid_implements_value_naming_no_implement_is_refused() -> None:
    document = a_document()
    document["location"]["gym"]["implements"]["cable"] = "pulley"

    error = refusal(document)

    assert "location.gym.implements.cable" in error.message
    assert "pulley" in error.message


@pytest.mark.parametrize(
    ("fact", "value"),
    [
        ("units", "stone"),
        ("bodyweight_units", 70),
        ("week_starts", "funday"),
        ("timezone", ""),
        ("available_days", ["monday", "monday"]),
        ("available_days", []),
        ("available_days", "monday"),
        ("session_minutes", 0),
        ("session_minutes", 45.5),
        ("session_minutes", True),
        ("checkin_cadence_days", -7),
    ],
)
def test_an_athlete_fact_of_the_wrong_shape_is_refused_naming_it(fact: str, value: Any) -> None:
    document = a_document()
    document["athlete"][fact] = value

    error = refusal(document)

    assert f"athlete.{fact}" in error.message


@pytest.mark.parametrize("fact", sorted(set(ATHLETE) - {"checkin_cadence_days"}))
def test_a_missing_athlete_fact_is_refused_naming_it(fact: str) -> None:
    document = a_document()
    del document["athlete"][fact]

    error = refusal(document)

    assert f"athlete.{fact}" in error.message


def test_a_missing_athlete_table_is_refused() -> None:
    document = a_document()
    del document["athlete"]

    assert "athlete" in refusal(document).message


@pytest.mark.parametrize(
    "implement",
    [
        {},
        {"increment": 2.5, "rack": [5, 10]},
        {"increment": 0},
        {"increment": "2.5"},
        {"rack": []},
        {"rack": [5, "ten"]},
        {"rack": [5, True]},
        {"increment": 2.5, "base": 20, "max": 10},
    ],
)
def test_a_grid_implement_of_the_wrong_shape_is_refused(implement: dict[str, Any]) -> None:
    document = a_document()
    document["location"]["gym"]["implement"]["bar"] = implement

    error = refusal(document)

    assert "location.gym.implement.bar" in error.message


@pytest.mark.parametrize(
    ("key", "value"),
    [("kind", "garage"), ("dumbbells", "three"), ("kit", ""), ("collars", 1)],
)
def test_a_location_of_the_wrong_shape_is_refused(key: str, value: Any) -> None:
    document = a_document()
    document["location"]["home"][key] = value

    error = refusal(document)

    assert f"location.home.{key}" in error.message


def test_a_missing_engine_version_is_refused_naming_it() -> None:
    error = refusal(a_document(engine={}))

    assert "engine.version" in error.message
