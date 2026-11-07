"""A structural check of a parsed TOML document against the JSON Schema 2020-12 subset the Draft
schemas use. A TOML date stands for a `format: date` string."""

import datetime
import re
from typing import cast

type Json = dict[str, object]

TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}
KNOWN = {
    "$schema",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "prefixItems",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "minLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
    "anyOf",
    "oneOf",
    "description",
}


def problems(value: object, schema: Json, at: str = "$") -> list[str]:
    """Every place `value` breaks `schema`; empty when it conforms."""
    unknown = set(schema) - KNOWN
    if unknown:
        return [f"{at}: the checker does not know {sorted(unknown)}"]
    found: list[str] = []
    if "type" in schema and not _is_type(value, str(schema["type"]), schema):
        return [f"{at}: {value!r} is not {schema['type']}"]
    if "enum" in schema and value not in cast(list[object], schema["enum"]):
        found.append(f"{at}: {value!r} is not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        found.append(f"{at}: {value!r} is not {schema['const']!r}")
    found += _number(value, schema, at)
    found += _string(value, schema, at)
    if isinstance(value, dict):
        found += _object(cast(Json, value), schema, at)
    if isinstance(value, list):
        found += _array(cast(list[object], value), schema, at)
    if "anyOf" in schema:
        matches = [problems(cast(object, value), s, at) for s in cast(list[Json], schema["anyOf"])]
        if all(matches):
            found.append(f"{at}: matches no anyOf branch: {matches}")
    if "oneOf" in schema:
        matches = [problems(cast(object, value), s, at) for s in cast(list[Json], schema["oneOf"])]
        if sum(1 for m in matches if not m) != 1:
            found.append(f"{at}: matches {sum(1 for m in matches if not m)} oneOf branches")
    return found


def _is_type(value: object, name: str, schema: Json) -> bool:
    if isinstance(value, bool) and name in ("integer", "number"):
        return False
    if name == "string" and schema.get("format") == "date" and type(value) is datetime.date:
        return True
    return isinstance(value, TYPES[name])


def _number(value: object, schema: Json, at: str) -> list[str]:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return []
    found: list[str] = []
    if "minimum" in schema and value < cast(float, schema["minimum"]):
        found.append(f"{at}: {value} is below {schema['minimum']}")
    if "maximum" in schema and value > cast(float, schema["maximum"]):
        found.append(f"{at}: {value} is above {schema['maximum']}")
    if "exclusiveMinimum" in schema and value <= cast(float, schema["exclusiveMinimum"]):
        found.append(f"{at}: {value} is not above {schema['exclusiveMinimum']}")
    return found


def _string(value: object, schema: Json, at: str) -> list[str]:
    if not isinstance(value, str):
        return []
    found: list[str] = []
    if len(value) < cast(int, schema.get("minLength", 0)):
        found.append(f"{at}: {value!r} is too short")
    if "pattern" in schema and not re.search(str(schema["pattern"]), value):
        found.append(f"{at}: {value!r} does not match {schema['pattern']}")
    if schema.get("format") == "date":
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            found.append(f"{at}: {value!r} is not a date")
    return found


def _object(value: Json, schema: Json, at: str) -> list[str]:
    found: list[str] = []
    properties = cast(dict[str, Json], schema.get("properties", {}))
    for key in cast(list[str], schema.get("required", [])):
        if key not in value:
            found.append(f"{at}: {key} is required")
    extra = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in properties:
            found += problems(item, properties[key], f"{at}.{key}")
        elif extra is False:
            found.append(f"{at}: {key} is not allowed")
        elif isinstance(extra, dict):
            found += problems(item, cast(Json, extra), f"{at}.{key}")
    return found


def _array(value: list[object], schema: Json, at: str) -> list[str]:
    found: list[str] = []
    if len(value) < cast(int, schema.get("minItems", 0)):
        found.append(f"{at}: fewer than {schema['minItems']} items")
    if "maxItems" in schema and len(value) > cast(int, schema["maxItems"]):
        found.append(f"{at}: more than {schema['maxItems']} items")
    prefix = cast(list[Json], schema.get("prefixItems", []))
    for index, item in enumerate(value):
        if index < len(prefix):
            found += problems(item, prefix[index], f"{at}[{index}]")
        elif "items" in schema:
            found += problems(item, cast(Json, schema["items"]), f"{at}[{index}]")
    return found
