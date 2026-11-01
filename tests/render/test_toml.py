import datetime
import tomllib
from typing import cast

import pytest

from coach.render.toml import TomlValue, dumps


def test_scalars_round_trip() -> None:
    document = {
        "name": "Joe",
        "count": 3,
        "negative": -42,
        "big": 2**62,
        "ratio": 2.5,
        "whole_float": 20.0,
        "tiny": 1e-300,
        "huge": 1.5e300,
        "on": True,
        "off": False,
        "day": datetime.date(2026, 11, 2),
        "moment": datetime.datetime(2026, 11, 2, 7, 30, 15),
        "aware": datetime.datetime(2026, 11, 2, 7, 30, tzinfo=datetime.UTC),
    }

    assert tomllib.loads(dumps(document)) == document


@pytest.mark.parametrize(
    "text",
    [
        "",
        'say "hi"',
        "back\\slash",
        "tab\there",
        "bell\x07 and del\x7f",
        "ünïcode ✓",
        "line one\nline two",
        'ends with a quote"',
        'triple """ inside\nand more',
        "trailing newline\n",
        "\nleading newline",
        "crlf\r\nline",
        "back\\slash\nand \\n literal",
    ],
)
def test_strings_round_trip(text: str) -> None:
    document = {"text": text}

    assert tomllib.loads(dumps(document)) == document


def test_a_string_with_a_newline_is_written_multi_line() -> None:
    emitted = dumps({"read": "first\nsecond"})

    assert '"""' in emitted
    assert "first\nsecond" in emitted


@pytest.mark.parametrize("key", ["plain_key-1", "has space", "", "ünï", "a.b", '"quoted"'])
def test_keys_needing_quotes_round_trip(key: str) -> None:
    document = {key: 1, "table": {key: {key: "x"}}}

    assert tomllib.loads(dumps(document)) == document


def test_arrays_round_trip() -> None:
    document = {
        "days": ["monday", "thursday"],
        "loads": [4, 6, 12.5],
        "empty": [],
        "nested": [[1, 2], ["a"], []],
        "dates": [datetime.date(2026, 1, 1)],
    }

    assert tomllib.loads(dumps(document)) == document


def test_tables_and_arrays_of_tables_round_trip() -> None:
    document = {
        "title": "plan",
        "engine": {"version": "0.3.0"},
        "hevy": {},
        "location": {
            "gym": {
                "kind": "grid",
                "implements": {"barbell": "bar"},
                "implement": {"bar": {"increment": 2.5, "base": 20}, "rack": {"rack": [4, 6]}},
            }
        },
        "line": [
            {"exercise": "squat", "sets": 3, "set": [{"reps": 5}, {"reps": 3}]},
            {"exercise": "bench", "notes": {"why": "a\nb"}},
        ],
        "empty_list_of_tables": [],
    }

    assert tomllib.loads(dumps(document)) == document


def test_a_table_key_after_a_sub_table_stays_in_its_table() -> None:
    document = {"a": {"sub": {"x": 1}, "y": 2}, "z": 3}

    assert tomllib.loads(dumps(document)) == document


@pytest.mark.parametrize(
    "value", [None, {1, 2}, object(), [{"a": 1}, 2], [[{"a": 1}]], float("nan")]
)
def test_a_value_toml_cannot_hold_is_refused(value: object) -> None:
    with pytest.raises(TypeError):
        dumps({"bad": cast(TomlValue, value)})
