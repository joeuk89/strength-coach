import datetime
import math
import re
from collections.abc import Mapping, Sequence
from typing import cast

type TomlValue = (
    str
    | bool
    | int
    | float
    | datetime.date
    | datetime.datetime
    | Sequence[TomlValue]
    | Mapping[str, TomlValue]
)

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\f": "\\f", "\r": "\\r"}


def dumps(document: Mapping[str, TomlValue]) -> str:
    """`document` as TOML that `tomllib.loads` reads back equal."""
    lines: list[str] = []
    _emit_table(document, (), lines, header=None)
    return "\n".join(lines) + "\n" if lines else ""


def _emit_table(
    table: Mapping[str, object], path: tuple[str, ...], lines: list[str], header: str | None
) -> None:
    if header is not None:
        if lines:
            lines.append("")
        lines.append(header)
    nested: list[tuple[str, object]] = []
    for key, value in table.items():
        if _is_table(value) or _is_array_of_tables(value):
            nested.append((key, value))
        else:
            lines.append(f"{_key(key)} = {_inline(value)}")
    for key, value in nested:
        child = (*path, key)
        dotted = ".".join(_key(part) for part in child)
        if _is_table(value):
            _emit_table(_as_table(value), child, lines, header=f"[{dotted}]")
        else:
            for item in _as_sequence(value):
                _emit_table(_as_table(item), child, lines, header=f"[[{dotted}]]")


def _is_table(value: object) -> bool:
    return isinstance(value, Mapping)


def _is_array_of_tables(value: object) -> bool:
    if not _is_sequence(value):
        return False
    items = _as_sequence(value)
    if not items or not any(isinstance(item, Mapping) for item in items):
        return False
    if not all(isinstance(item, Mapping) for item in items):
        raise TypeError("an array mixes tables with other values")
    return True


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str)


def _inline(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            raise TypeError("NaN does not round-trip")
        return repr(value)
    if isinstance(value, str):
        return _multi_line(value) if "\n" in value else _basic(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if _is_sequence(value):
        items = _as_sequence(value)
        if any(isinstance(item, Mapping) for item in items):
            raise TypeError("a table inside an inline array is not supported")
        return "[" + ", ".join(_inline(item) for item in items) + "]"
    raise TypeError(f"TOML cannot hold {type(value).__name__}")


def _key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else _basic(key)


def _basic(text: str) -> str:
    return '"' + "".join(_escape(c) for c in text) + '"'


def _multi_line(text: str) -> str:
    # The newline after the opening quotes is trimmed by TOML, so a leading newline survives.
    body = "".join(c if c == "\n" else _escape(c) for c in text)
    return '"""\n' + body + '"""'


def _escape(char: str) -> str:
    if char in _ESCAPES:
        return _ESCAPES[char]
    if char < " " or char == "\x7f":
        return f"\\u{ord(char):04x}"
    return char


def _as_table(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value)


def _as_sequence(value: object) -> Sequence[object]:
    return cast(Sequence[object], value)
