"""Typed facts as markdown: scalars as bullets, a list of rows as a table."""

from collections.abc import Mapping, Sequence
from typing import cast

from coach.render.markdown import bullets, cell, table

LABELS = {"average_14_days": "14-day average", "e1rm": "e1RM", "e1rm_before": "e1RM before"}


def facts_text(facts: Mapping[str, object]) -> str:
    scalars: list[str] = []
    tables: list[str] = []
    for key, value in facts.items():
        label = _label(key)
        if _is_rows(value):
            rows = cast(Sequence[Mapping[str, object]], value)
            columns = list(dict.fromkeys(k for row in rows for k in row))
            tables.append(
                f"**{label}**\n\n"
                + table(
                    [_label(c) for c in columns],
                    [[row.get(c) for c in columns] for row in rows],
                )
            )
        else:
            scalars.append(f"{label}: {cell(value)}")
    return "\n\n".join(part for part in (bullets(scalars), *tables) if part)


def _is_rows(value: object) -> bool:
    if not isinstance(value, list | tuple) or not value:
        return False
    return all(isinstance(item, Mapping) for item in cast(Sequence[object], value))


def _label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " "))
