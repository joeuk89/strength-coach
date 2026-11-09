import hashlib
import math
from typing import cast

from coach.core.draft_reader import Reader, Table
from coach.core.draft_schema import TEXTS, Json, Location
from coach.core.errors import Invalid
from coach.core.ref import KEY, REF_KINDS, Ref
from coach.core.registries.registry import Entry, Registry

KEY_SHAPE: Json = {"type": "string", "pattern": f"^{KEY.pattern}$"}


def draft_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def number_shape(low: float) -> Json:
    return {"type": "number", "minimum": low} if math.isfinite(low) else {"type": "number"}


def ref_shape(kinds: tuple[str, ...]) -> Json:
    """`kind:id`, or `kind:@key` citing a record the same Draft raises."""
    return {"type": "string", "pattern": f"^({'|'.join(kinds)}):(@{KEY.pattern}|[^@].*)$"}


class Fields(Reader):
    """Reads one table's values by type, and refuses any key nobody read."""

    def __init__(self, table: Table, where: str, *, at: Location | None = None) -> None:
        super().__init__(table, at=at)
        self.where = where

    def _where(self, key: str) -> str:
        return f"{self.where}: {key}"

    def _child(self, table: Table, key: str, index: int | None, at: Location) -> "Fields":
        where = f"{self.where} {key}" if index is None else f"{self.where} {key} #{index}"
        return Fields(table, where, at=at)

    def number(self, name: str, *, required: bool = False, low: float = 0.0) -> float | None:
        value = self._present(name, number_shape(low), required=required)
        if value is None:
            return None
        if isinstance(value, int | float) and not isinstance(value, bool) and value >= low:
            return float(value)
        raise self.wrong(name, f"a number of at least {low:g}")

    def term(self, name: str, registry: Registry[Entry], *, required: bool = False) -> str | None:
        return self.choice(name, registry.names(), required=required)

    def ref(self, name: str, kinds: tuple[str, ...]) -> Ref | None:
        value = self._string(name, ref_shape(kinds))
        if value is None:
            return None
        ref = Ref.parse(value)
        if ref.kind not in kinds:
            raise self.wrong(name, f"a ref to one of {', '.join(kinds)}")
        return ref

    def refs(self, name: str) -> tuple[Ref, ...]:
        value = self._typed(name, {"type": "array", "items": ref_shape(REF_KINDS)})
        if value is None:
            return ()
        if not isinstance(value, list) or not all(
            isinstance(v, str) for v in cast(list[object], value)
        ):
            raise self.wrong(name, "a list of refs")
        return tuple(Ref.parse(v) for v in cast(list[str], value))

    def texts(self, name: str) -> tuple[str, ...]:
        value = self._typed(name, TEXTS)
        if value is None:
            return ()
        if isinstance(value, list) and all(
            isinstance(v, str) and v for v in cast(list[object], value)
        ):
            return tuple(cast(list[str], value))
        raise self.wrong(name, "a list of non-empty strings")

    def key(self) -> str | None:
        return self._string("key", KEY_SHAPE)

    def done[R](self, record: R) -> R:
        unknown = sorted(set(self.values) - self.read)
        if unknown:
            raise Invalid("unknown_key", f"{self.where}: unknown key {', '.join(unknown)}")
        return record

    def only(self, *names: str) -> None:
        extra = sorted(set(self.values) - set(names))
        if extra:
            raise Invalid(
                "unknown_key",
                f"{self.where}: a withdrawing row carries only withdraws; drop {', '.join(extra)}",
            )


def required[T](value: T | None) -> T:
    assert value is not None
    return value
