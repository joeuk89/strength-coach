import copy
import json
from collections.abc import Sequence
from typing import cast

from coach.cli.declaration import Json
from coach.core.errors import Invalid
from coach.core.notice import Notice


def success(
    schema_version: int, verb: str | None, result: Json, warnings: Sequence[Notice]
) -> Json:
    return {
        "schema_version": schema_version,
        "ok": True,
        "verb": verb,
        "result": result,
        "warnings": [_notice(w) for w in warnings],
    }


def failure(
    schema_version: int, verb: str | None, notice: Notice, warnings: Sequence[Notice]
) -> Json:
    return {
        "schema_version": schema_version,
        "ok": False,
        "verb": verb,
        "error": _notice(notice),
        "warnings": [_notice(w) for w in warnings],
    }


def render(envelope: Json, *, pretty: bool) -> str:
    if pretty:
        return json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False) + "\n"


def project(result: Json, paths: Sequence[str]) -> Json:
    """Keep only the dotted `paths` of `result`, nested as they were."""
    projected: Json = {}
    for path in paths:
        *parents, leaf = path.split(".")
        target = projected
        for key in parents:
            child = target.setdefault(key, {})
            assert isinstance(child, dict)
            target = cast(Json, child)
        target[leaf] = copy.deepcopy(_lookup(result, path))
    return projected


def _lookup(result: object, path: str) -> object:
    value = result
    for key in path.split("."):
        mapping = cast(Json, value) if isinstance(value, dict) else {}
        if key not in mapping:
            raise Invalid("invalid_argument", f"--fields: result has no {path!r}")
        value = mapping[key]
    return value


def _notice(notice: Notice) -> Json:
    return {"code": notice.code, "message": notice.message}
