import copy
import json
from collections.abc import Sequence
from typing import cast

from coach.cli.declaration import Json
from coach.core.errors import Invalid
from coach.core.flag import Flag
from coach.core.message import Message


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
    return {"code": message.code, "message": message.message}


def _warning(warning: Message | Flag) -> Json:
    return warning.to_json() if isinstance(warning, Flag) else _message(warning)
