"""What the athlete calls a session or an exercise, the one lookup every label, page and message
that names them reads."""

from collections.abc import Mapping


def named(names: Mapping[str, str], id_: str) -> str:
    """An id with no name stands for itself."""
    return names.get(id_, id_)
