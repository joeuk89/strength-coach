"""One table of a Draft read by type. Under a recording (`draft_schema`) every accessor notes its
key and shape, since each reaches a value through `_typed` or `raw`. Reading `values` directly
skips the note."""

import datetime
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Literal, Self, cast, overload

from coach.core import draft_schema
from coach.core.draft_schema import (
    BOOLEAN,
    DATE,
    TABLE,
    TEXT,
    Json,
    Location,
    Named,
    Step,
    enum,
    tables,
)
from coach.core.errors import Invalid

type Table = Mapping[str, object]

WHOLE: Json = {"type": "integer", "minimum": 0}


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Reader(ABC):
    """A subclass says where its table sits, for errors and for child tables, and adds the
    accessors only its own Draft needs. A key the document chose, from `names` or a subclass's
    list of names, notes the table's `additionalProperties`."""

    def __init__(self, values: Table, *, at: Location | None = None) -> None:
        self.values = values
        self.read: set[str] = set()
        self.chosen: set[str] = set()
        self._recording = draft_schema.current()
        self.at = self._recording.visit(values, at) if self._recording else at or ()

    @abstractmethod
    def _where(self, key: str) -> str: ...

    @abstractmethod
    def _child(self, table: Table, key: str, index: int | None, at: Location) -> Self: ...

    def names(self) -> list[str]:
        self.read.update(self.values)
        self.chosen.update(self.values)
        return list(self.values)

    def has(self, key: str) -> bool:
        if self._recording:
            self._recording.note(self.at, self._step(key), None, presence=True)
        return key in self.values

    def raw(self, key: str) -> object | None:
        self.read.add(key)
        value = self.values.get(key)
        if self._recording:
            self._recording.note(self.at, self._step(key), None)
            self._recording.place(value, (*self.at, self._step(key)))
        return value

    def missing(self, key: str) -> Invalid:
        return Invalid("invalid_argument", f"{self._where(key)} is required")

    def wrong(self, key: str, wanted: str) -> Invalid:
        return Invalid("invalid_argument", f"{self._where(key)} must be {wanted}")

    @overload
    def text(self, key: str, *, required: Literal[True]) -> str: ...
    @overload
    def text(self, key: str, *, required: bool = False) -> str | None: ...
    def text(self, key: str, *, required: bool = False) -> str | None:
        return self._string(key, TEXT, required=required)

    @overload
    def choice(self, key: str, choices: Sequence[str], *, required: Literal[True]) -> str: ...
    @overload
    def choice(self, key: str, choices: Sequence[str], *, required: bool = False) -> str | None: ...
    def choice(self, key: str, choices: Sequence[str], *, required: bool = False) -> str | None:
        value = self._string(key, enum(choices), required=required, value=self.values.get(key))
        if value is None or value in choices:
            return value
        raise self.wrong(key, f"one of {', '.join(choices)}")

    @overload
    def whole(self, key: str, *, required: Literal[True]) -> int: ...
    @overload
    def whole(self, key: str, *, required: bool = False) -> int | None: ...
    def whole(self, key: str, *, required: bool = False) -> int | None:
        value = self._present(key, WHOLE, required=required)
        if value is None or (is_int(value) and cast(int, value) >= 0):
            return cast(int | None, value)
        raise self.wrong(key, "a whole number of at least 0")

    def boolean(self, key: str, *, required: bool = False) -> bool | None:
        value = self._present(key, BOOLEAN, required=required)
        if value is None or isinstance(value, bool):
            return value
        raise self.wrong(key, "true or false")

    def date(self, key: str, *, required: bool = False) -> datetime.date | None:
        value = self._present(key, DATE, required=required)
        if value is None or type(value) is datetime.date:
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value)
            except ValueError:
                pass
        raise self.wrong(key, "a date, 2026-10-30")

    @overload
    def table(self, key: str, *, required: Literal[True]) -> Self: ...
    @overload
    def table(self, key: str, *, required: bool = False) -> Self | None: ...
    def table(self, key: str, *, required: bool = False) -> Self | None:
        value = self._present(key, TABLE, required=required)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise self.wrong(key, "a table")
        return self._child(cast(Table, value), key, None, (*self.at, self._step(key)))

    def tables(self, key: str, *, required: bool = False, at_least_one: bool = False) -> list[Self]:
        value = self._typed(key, tables(at_least_one=at_least_one), required=required)
        if value is None and not required:
            return []
        items = cast(Sequence[object], value) if isinstance(value, list | tuple) else None
        if at_least_one and not items:
            raise self.wrong(key, "an array of tables with at least one entry")
        if items is None or not all(isinstance(item, Mapping) for item in items):
            raise self.wrong(key, "an array of tables")
        return [
            self._child(cast(Table, item), key, i, (*self.at, self._step(key), i))
            for i, item in enumerate(items, start=1)
        ]

    def _typed(
        self, key: str, shape: Json, *, required: bool = False, value: object = None
    ) -> object | None:
        """The value of `key`, its shape noted. `value` is what the recording keeps of a choice."""
        if self._recording:
            self._recording.note(self.at, self._step(key), shape, required=required, value=value)
        return self.raw(key)

    def _present(
        self, key: str, shape: Json, *, required: bool = False, value: object = None
    ) -> object | None:
        found = self._typed(key, shape, required=required, value=value)
        if found is None and required:
            raise self.missing(key)
        return found

    def _string(
        self, key: str, shape: Json, *, required: bool = False, value: object = None
    ) -> str | None:
        found = self._present(key, shape, required=required, value=value)
        if found is None or (isinstance(found, str) and found):
            return found
        raise self.wrong(key, "a non-empty string")

    def _step(self, key: str) -> Step:
        return Named(key) if key in self.chosen else key
