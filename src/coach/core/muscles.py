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


# The muscles a version's per-muscle dose is judged on; the smaller ones (forearms, traps,
# adductors, lower back) are trained indirectly and never asked for by name.
DOSED_MUSCLES = (
    "chest",
    "lats",
    "upper_back",
    "front_delts",
    "side_delts",
    "rear_delts",
    "biceps",
    "triceps",
    "quadriceps",
    "hamstrings",
    "glutes",
    "calves",
    "abdominals",
)
