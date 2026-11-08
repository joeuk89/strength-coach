import datetime
import tomllib
from typing import Any, Self

import pytest

from coach.core.draft_reader import Reader
from coach.core.draft_schema import Location, record
from coach.core.errors import Invalid


class Sheet(Reader):
    """A parser's reader: where a table sits is all the base needs told, plus any accessor of
    its own, which reads through `_typed`."""

    def _where(self, key: str) -> str:
        return f"sheet: {key}"

    def _child(self, table: Any, key: str, index: int | None, at: Location) -> Self:
        return type(self)(table, at=at)

    def tint(self, key: str) -> object:
        return self._typed(key, {"const": "tint"}, required=True)


def a_sheet(text: str) -> Sheet:
    return Sheet(tomllib.loads(text))


def schema_of(read: Any, *documents: str) -> Any:
    return record(lambda data: read(a_sheet(data.decode())), documents).schema()


def test_an_accessor_a_parser_adds_records_itself() -> None:
    def read(s: Sheet) -> None:
        s.tint("colour")

    schema = schema_of(read, 'colour = "red"')

    assert schema["properties"]["colour"] == {"const": "tint"}
    assert schema["required"] == ["colour"]


def test_each_shared_accessor_records_its_shape_and_whether_it_is_required() -> None:
    def read(s: Sheet) -> None:
        s.text("name", required=True)
        s.text("note")
        s.whole("count", required=True)
        s.boolean("flag")
        s.date("on")
        s.choice("size", ("s", "l"))

    schema = schema_of(read, 'name = "a"\ncount = 1\nflag = true\non = 2026-11-02\nsize = "s"')

    assert schema["properties"] == {
        "name": {"type": "string", "minLength": 1},
        "note": {"type": "string", "minLength": 1},
        "count": {"type": "integer", "minimum": 0},
        "flag": {"type": "boolean"},
        "on": {"type": "string", "format": "date"},
        "size": {"enum": ["s", "l"]},
    }
    assert schema["required"] == ["name", "count"]


def test_a_child_table_records_under_its_parent() -> None:
    def read(s: Sheet) -> None:
        brush = s.table("brush", required=True)
        brush.whole("width", required=True)
        for coat in s.tables("coats", at_least_one=True):
            coat.text("paint")

    schema = schema_of(read, 'brush = { width = 2 }\n[[coats]]\npaint = "red"')

    assert schema["properties"]["brush"]["required"] == ["width"]
    assert schema["properties"]["coats"]["minItems"] == 1
    assert schema["properties"]["coats"]["items"]["properties"]["paint"]["type"] == "string"


def test_a_key_the_document_chose_records_as_additional_properties() -> None:
    def read(s: Sheet) -> None:
        for name in s.names():
            s.whole(name)

    schema = schema_of(read, "bench = 3")

    assert schema["properties"] == {}
    assert schema["additionalProperties"] == {"type": "integer", "minimum": 0}


def test_a_required_key_left_out_is_named() -> None:
    with pytest.raises(Invalid, match="sheet: name is required"):
        a_sheet("").text("name", required=True)


@pytest.mark.parametrize("document", ['v = ""', "v = 3"])
def test_a_text_of_the_wrong_kind_says_what_it_wants(document: str) -> None:
    with pytest.raises(Invalid, match="sheet: v must be a non-empty string"):
        a_sheet(document).text("v")


def test_a_value_is_read_back_by_its_type() -> None:
    sheet = a_sheet('name = "a"\ncount = 0\nflag = false\non = "2026-11-02"\nsize = "l"')

    assert sheet.text("name") == "a"
    assert sheet.whole("count") == 0
    assert sheet.boolean("flag") is False
    assert sheet.date("on") == datetime.date(2026, 11, 2)
    assert sheet.choice("size", ("s", "l")) == "l"
    assert sheet.text("absent") is None
    assert sheet.tables("absent_tables") == []
    assert sheet.table("absent_table") is None
