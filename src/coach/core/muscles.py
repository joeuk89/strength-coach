"""An Exercise's `muscles` value, exactly `{primary = [...], secondary = [...]}`."""

from typing import cast

MUSCLES_WANTED = "a table {primary = [...], secondary = [...]} of muscle names"


def read_muscles(value: object) -> dict[str, list[str]] | None:
    """The primary and secondary muscle lists, or None when the value has any other shape."""
    if not isinstance(value, dict):
        return None
    table = cast(dict[str, object], value)
    if set(table) != {"primary", "secondary"}:
        return None
    muscles: dict[str, list[str]] = {}
    for part in ("primary", "secondary"):
        names = table[part]
        if not isinstance(names, list) or not all(
            isinstance(n, str) for n in cast(list[object], names)
        ):
            return None
        muscles[part] = list(cast(list[str], names))
    return muscles
