import tomllib
from typing import Any

from coach.core.draft_fields import Fields, required
from coach.core.draft_schema import record
from coach.core.registries.registry import terms

COLOURS = terms("colours", "red", "blue")


def read_paint(data: bytes) -> object:
    f = Fields(tomllib.loads(data.decode()), "paint")
    colour = required(f.term("colour", COLOURS, required=True))
    shade = f.text("shade", required=colour == "red")
    coats = tuple(_coat(c) for c in f.tables("coats"))
    brush = f.subtable("brush")
    return f.done((colour, shade, coats, _brush(brush) if brush else None))


def _coat(f: Fields) -> object:
    return f.done((f.number("litres", required=True, low=0.5), f.date("dried")))


def _brush(f: Fields) -> object:
    return f.done(f.integer("width", required=True))


def test_a_required_read_is_a_required_property_of_its_type() -> None:
    schema: Any = record(read_paint, ['colour = "blue"']).schema()

    assert schema["properties"]["colour"] == {"enum": ["red", "blue"]}
    assert schema["required"] == ["colour"]
    assert schema["additionalProperties"] is False


def test_a_key_required_only_on_one_branch_is_optional() -> None:
    schema: Any = record(read_paint, ['colour = "red"\nshade = "dark"', 'colour = "blue"']).schema()

    assert schema["properties"]["shade"] == {"type": "string", "minLength": 1}
    assert "shade" not in schema["required"]


def test_an_array_of_tables_holds_the_shape_its_items_were_read_with() -> None:
    schema: Any = record(
        read_paint, ['colour = "blue"\n[[coats]]\nlitres = 1.5\ndried = 2026-11-02']
    ).schema()

    assert schema["properties"]["coats"] == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "litres": {"type": "number", "minimum": 0.5},
                "dried": {"type": "string", "format": "date"},
            },
            "required": ["litres"],
            "additionalProperties": False,
        },
    }


def test_a_table_no_document_entered_is_unreached() -> None:
    recording = record(read_paint, ['colour = "blue"'])

    assert recording.unreached() == ["brush", "coats"]


def test_a_table_entered_once_is_reached() -> None:
    recording = record(
        read_paint, ['colour = "blue"\nbrush = { width = 2 }\n[[coats]]\nlitres = 1']
    )

    assert recording.unreached() == []
    schema: Any = recording.schema()
    assert schema["properties"]["brush"]["required"] == ["width"]


def test_the_values_each_choice_took_are_kept() -> None:
    recording = record(read_paint, ['colour = "blue"', 'colour = "red"\nshade = "dark"'])

    assert recording.values((), "colour") == {"red", "blue"}


def read_withdrawable(data: bytes) -> object:
    f = Fields(tomllib.loads(data.decode()), "reading")
    if f.has("withdraws"):
        return f.done(f.text("withdraws", required=True))
    return f.done(f.number("kg", required=True))


def test_a_key_read_only_once_its_presence_is_tested_is_optional() -> None:
    schema: Any = record(read_withdrawable, ['withdraws = "wi-0001"']).schema()

    assert schema["properties"]["withdraws"] == {"type": "string", "minLength": 1}
    assert schema["required"] == []


def test_a_key_read_in_some_tables_only_is_optional() -> None:
    schema: Any = record(read_withdrawable, ['withdraws = "wi-0001"', "kg = 80"]).schema()

    assert schema["required"] == []
    assert set(schema["properties"]) == {"withdraws", "kg"}


def test_reading_outside_a_recording_records_nothing() -> None:
    read_paint(b'colour = "blue"')

    assert record(read_paint, []).schema()["properties"] == {}
