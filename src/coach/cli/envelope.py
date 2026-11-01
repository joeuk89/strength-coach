import copy
import json
from collections.abc import Sequence
from typing import cast

from coach.cli.declaration import Json
from coach.core.errors import Invalid
from coach.core.flag import Flag
from coach.core.message import Message

# verbs.md, "Envelope and budget".
BUDGET_BYTES = 3 * 1024


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
    """Cut trailing rows from the `{rows, count, truncated}` lists of the result, the longest
    first, until the envelope fits the budget; fields never drop."""
    fitted = copy.deepcopy(envelope)
    lists = _row_lists(fitted.get("result"))
    while _size(fitted) > BUDGET_BYTES:
        longest = max(lists, key=lambda found: len(_rows(found)), default=None)
        if longest is None or not _rows(longest):
            break
        _rows(longest).pop()
        longest["truncated"] = True
    return fitted


def _size(envelope: Json) -> int:
    return len(render(envelope, pretty=False).encode("utf-8"))


def _row_lists(value: object) -> list[Json]:
    if isinstance(value, list):
        return [found for item in cast(list[object], value) for found in _row_lists(item)]
    if not isinstance(value, dict):
        return []
    mapping = cast(Json, value)
    found = [mapping] if _is_row_list(mapping) else []
    return found + [nested for child in mapping.values() for nested in _row_lists(child)]


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
            raise Invalid("invalid_argument", f"--fields: result has no {path!r}")
        value = mapping[key]
    return value


def _message(message: Message) -> Json:
    return {"code": message.code, "message": message.message, **message.details}


def _warning(warning: Message | Flag) -> Json:
    return warning.to_json() if isinstance(warning, Flag) else _message(warning)
