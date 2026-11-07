import datetime
import hashlib
from collections.abc import Mapping
from typing import cast

from coach.core import draft_schema
from coach.core.draft_schema import BOOLEAN, DATE, TABLE, TEXT, TEXTS, Json, Location, enum, tables
from coach.core.errors import Invalid
from coach.core.ref import KEY, REF_KINDS, Ref
from coach.core.registries.registry import Entry, Registry

type Table = Mapping[str, object]

KEY_SHAPE: Json = {"type": "string", "pattern": f"^{KEY.pattern}$"}


def draft_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def ref_shape(kinds: tuple[str, ...]) -> Json:
    """`kind:id`, or `kind:@key` citing a record the same Draft raises."""
    return {"type": "string", "pattern": f"^({'|'.join(kinds)}):(@{KEY.pattern}|[^@].*)$"}


class Fields:
    """Reads one table's values by type, and refuses any key nobody read. Under a recording
    (`draft_schema`) each read also notes its key's shape."""

    def __init__(self, table: Table, where: str, *, at: Location | None = None) -> None:
        self.table = table
        self.where = where
        self.read: set[str] = set()
        self.recording = draft_schema.current()
        self.at = self.recording.visit(table, at) if self.recording else at or ()

    def has(self, name: str) -> bool:
        if self.recording:
            self.recording.note(self.at, name, None, presence=True)
        return name in self.table

    def raw(self, name: str) -> object | None:
        self.read.add(name)
        value = self.table.get(name)
        if self.recording:
            self.recording.note(self.at, name, None)
            self.recording.place(value, (*self.at, name))
        return value

    def text(self, name: str, *, required: bool = False) -> str | None:
        self._note(name, TEXT, required)
        return self._text(name, required)

    def number(self, name: str, *, required: bool = False, low: float = 0.0) -> float | None:
        self._note(name, {"type": "number", "minimum": low}, required)
        value = self._value(name, required)
        if value is None:
            return None
        if isinstance(value, int | float) and not isinstance(value, bool) and value >= low:
            return float(value)
        raise self.wrong(name, f"a number of at least {low:g}")

    def integer(self, name: str, *, required: bool = False) -> int | None:
        self._note(name, {"type": "integer", "minimum": 0}, required)
        value = self._value(name, required)
        if value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
            return value
        raise self.wrong(name, "a whole number of at least 0")

    def boolean(self, name: str, *, required: bool = False) -> bool | None:
        self._note(name, BOOLEAN, required)
        value = self._value(name, required)
        if value is None or isinstance(value, bool):
            return value
        raise self.wrong(name, "true or false")

    def date(self, name: str, *, required: bool = False) -> datetime.date | None:
        self._note(name, DATE, required)
        value = self._value(name, required)
        if value is None or type(value) is datetime.date:
            return value
        if isinstance(value, str):
            try:
                return datetime.date.fromisoformat(value)
            except ValueError:
                pass
        raise self.wrong(name, "a date, 2026-10-30")

    def term(self, name: str, registry: Registry[Entry], *, required: bool = False) -> str | None:
        self._note(name, enum(registry.names()), required, self.table.get(name))
        value = self._text(name, required)
        if value is None or value in registry:
            return value
        raise self.wrong(name, f"one of {', '.join(registry.names())}")

    def choice(self, name: str, values: tuple[str, ...], *, required: bool = False) -> str | None:
        self._note(name, enum(values), required, self.table.get(name))
        value = self._text(name, required)
        if value is None or value in values:
            return value
        raise self.wrong(name, f"one of {', '.join(values)}")

    def ref(self, name: str, kinds: tuple[str, ...]) -> Ref | None:
        self._note(name, ref_shape(kinds))
        value = self._text(name, False)
        if value is None:
            return None
        ref = Ref.parse(value)
        if ref.kind not in kinds:
            raise self.wrong(name, f"a ref to one of {', '.join(kinds)}")
        return ref

    def refs(self, name: str) -> tuple[Ref, ...]:
        self._note(name, {"type": "array", "items": ref_shape(REF_KINDS)})
        value = self.raw(name)
        if value is None:
            return ()
        if not isinstance(value, list) or not all(
            isinstance(v, str) for v in cast(list[object], value)
        ):
            raise self.wrong(name, "a list of refs")
        return tuple(Ref.parse(v) for v in cast(list[str], value))

    def tables(self, name: str) -> list["Fields"]:
        self._note(name, tables())
        value = self.raw(name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(t, dict) for t in cast(list[object], value)
        ):
            raise self.wrong(name, "an array of tables")
        return [
            Fields(t, f"{self.where} {name} #{i}", at=(*self.at, name, i))
            for i, t in enumerate(cast(list[Table], value), 1)
        ]

    def texts(self, name: str) -> tuple[str, ...]:
        self._note(name, TEXTS)
        value = self.raw(name)
        if value is None:
            return ()
        if isinstance(value, list) and all(
            isinstance(v, str) and v for v in cast(list[object], value)
        ):
            return tuple(cast(list[str], value))
        raise self.wrong(name, "a list of non-empty strings")

    def subtable(self, name: str) -> "Fields | None":
        self._note(name, TABLE)
        value = self.raw(name)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise self.wrong(name, "a table")
        return Fields(cast(Table, value), f"{self.where} {name}", at=(*self.at, name))

    def key(self) -> str | None:
        self._note("key", KEY_SHAPE)
        return self._text("key", False)

    def done[R](self, record: R) -> R:
        unknown = sorted(set(self.table) - self.read)
        if unknown:
            raise Invalid("unknown_key", f"{self.where}: unknown key {', '.join(unknown)}")
        return record

    def only(self, *names: str) -> None:
        extra = sorted(set(self.table) - set(names))
        if extra:
            raise Invalid(
                "unknown_key",
                f"{self.where}: a withdrawing row carries only withdraws; drop {', '.join(extra)}",
            )

    def _note(self, name: str, shape: Json, required: bool = False, value: object = None) -> None:
        if self.recording:
            self.recording.note(self.at, name, shape, required=required, value=value)

    def _text(self, name: str, required: bool) -> str | None:
        value = self._value(name, required)
        if value is None or (isinstance(value, str) and value):
            return value
        raise self.wrong(name, "a non-empty string")

    def _value(self, name: str, required: bool) -> object | None:
        value = self.raw(name)
        if value is None and required:
            raise Invalid("invalid_argument", f"{self.where}: {name} is required")
        return value

    def wrong(self, name: str, wanted: str) -> Invalid:
        return Invalid("invalid_argument", f"{self.where}: {name} must be {wanted}")


def required[T](value: T | None) -> T:
    assert value is not None
    return value
