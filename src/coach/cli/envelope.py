import copy
import json
from collections.abc import Callable, Sequence
from typing import cast

from coach.cli.declaration import Json
from coach.core.errors import Invalid
from coach.core.flag import Flag
from coach.core.message import Message

# verbs.md, "Envelope and budget".
BUDGET_BYTES = 6 * 1024
ENVELOPE_FIELDS = {
    "schema_version": "it is always returned",
    "ok": "it is always returned",
    "verb": "it is always returned",
    "warnings": "it is always returned",
    "error": "it is returned on failure",
}


def success(
    schema_version: int, verb: str | None, result: Json, warnings: Sequence[Message | Flag]
) -> Json:
    return {
        "schema_version": schema_version,
        "ok": True,
        "verb": verb,
        "result": result,
        "warnings": [_warning(w) for w in warnings],
    }


def failure(
    schema_version: int, verb: str | None, error: Message, warnings: Sequence[Message | Flag]
) -> Json:
    return {
        "schema_version": schema_version,
        "ok": False,
        "verb": verb,
        "error": _message(error),
        "warnings": [_warning(w) for w in warnings],
    }


def render(envelope: Json, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False) + "\n"


def fit(envelope: Json) -> Json:
    """Cut trailing keys from the grouped rows of the result, the longest `keys[]` first, then
    trailing rows from its flat `{rows, count, truncated}` lists, the longest first, until the
    envelope fits the budget; fields and grouped rows never drop."""
    fitted = copy.deepcopy(envelope)
    mappings = _mappings(fitted.get("result"))
    groups = [found for found in mappings if _is_grouped_row(found)]
    lists = [
        found
        for found in mappings
        if _is_row_list(found) and not any(_is_grouped_row(row) for row in _rows(found))
    ]
    _cut(fitted, groups, _keys, "keys_truncated")
    _cut(fitted, lists, _rows, "truncated")
    return fitted


def _cut(
    envelope: Json, holders: list[Json], items: Callable[[Json], list[object]], marker: str
) -> None:
    while _size(envelope) > BUDGET_BYTES:
        longest = max(holders, key=lambda found: len(items(found)), default=None)
        if longest is None or not items(longest):
            break
        items(longest).pop()
        longest[marker] = True


def _size(envelope: Json) -> int:
    return len(render(envelope, pretty=False).encode("utf-8"))


def _mappings(value: object) -> list[Json]:
    if isinstance(value, list):
        return [found for item in cast(list[object], value) for found in _mappings(item)]
    if not isinstance(value, dict):
        return []
    mapping = cast(Json, value)
    return [mapping, *(nested for child in mapping.values() for nested in _mappings(child))]


def _is_grouped_row(row: object) -> bool:
    return isinstance(row, dict) and isinstance(cast(Json, row).get("keys"), list)


def _keys(row: Json) -> list[object]:
    return cast(list[object], row["keys"])


def _is_row_list(mapping: Json) -> bool:
    return (
        isinstance(mapping.get("rows"), list)
        and isinstance(mapping.get("count"), int)
        and isinstance(mapping.get("truncated"), bool)
    )


def _rows(row_list: Json) -> list[object]:
    return cast(list[object], row_list["rows"])


def project(result: Json, paths: Sequence[str]) -> Json:
    """Keep only the dotted `paths` of `result`, nested as they were."""
    projected: Json = {}
    for path in paths:
        value = _lookup(result, path)
        *parents, leaf = path.split(".")
        target = projected
        for key in parents:
            child = target.setdefault(key, {})
            if not isinstance(child, dict):
                raise Invalid("invalid_argument", f"--fields: {path!r} conflicts with another path")
            target = cast(Json, child)
        target[leaf] = copy.deepcopy(value)
    return projected


def _lookup(result: object, path: str) -> object:
    value = result
    for key in path.split("."):
        mapping = cast(Json, value) if isinstance(value, dict) else {}
        if key not in mapping:
            if value is result and key in ENVELOPE_FIELDS:
                raise Invalid(
                    "invalid_argument",
                    f"--fields: {key!r} is an envelope field, not in result; "
                    f"{ENVELOPE_FIELDS[key]}",
                )
            raise Invalid("invalid_argument", f"--fields: result has no {path!r}")
        value = mapping[key]
    return value


def _message(message: Message) -> Json:
    return {"code": message.code, "message": message.message, **message.details}


def _warning(warning: Message | Flag) -> Json:
    return warning.to_json() if isinstance(warning, Flag) else _message(warning)
