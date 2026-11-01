"""A line's scheme param: as authored on the line, else the registry default."""

from coach.core.program.form import SchemeRef
from coach.core.registries.schemes import SCHEMES


def number(scheme: SchemeRef, name: str) -> float:
    value = scheme.params.get(name)
    if value is None:
        param = SCHEMES.get(scheme.name).param(name)
        value = None if param is None else param.default
    if not isinstance(value, int | float):
        raise ValueError(f"{scheme.name} has no number {name}")
    return float(value)
