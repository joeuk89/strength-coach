"""The `rn:` registry test (ADR 0004, ADR 0020): every `rn:` ref in the registries and in the
source resolves to a current claim or a numbered section of a research note under `docs/spec/`.
It reads claim numbers and statuses and section headings, never a claim's text."""

import re
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import cast

from coach.core.registries import REGISTRIES

REF = re.compile(r"rn:[a-z0-9-]+(?:\.\d+| §\d+)?")
CLAIM = re.compile(r"rn:([a-z0-9-]+)\.(\d+)")
SECTION = re.compile(r"rn:([a-z0-9-]+) §(\d+)")
FRONT_MATTER = re.compile(r"\A<!-- coach:note\n(.*?)^-->", re.DOTALL | re.MULTILINE)


def refs_in_registries() -> set[str]:
    return {ref for registry in REGISTRIES for row in registry.rows() for ref in _strings(row)}


def refs_in_source(src: Path) -> set[str]:
    return {
        ref
        for path in sorted(src.rglob("*.py"))
        for ref in REF.findall(path.read_text(encoding="utf-8"))
    }


def problems(refs: Iterable[str], notes: Path) -> list[str]:
    return [f"{ref}: {problem}" for ref in sorted(refs) if (problem := _resolve(ref, notes))]


def _resolve(ref: str, notes: Path) -> str | None:
    if match := CLAIM.fullmatch(ref):
        return _claim(notes / f"{match.group(1)}.md", int(match.group(2)))
    if match := SECTION.fullmatch(ref):
        return _section(notes / f"{match.group(1)}.md", int(match.group(2)))
    return "not rn:<note>.<n> or rn:<note> §<n>"


def _claim(note: Path, n: int) -> str | None:
    if not note.is_file():
        return f"no note {note.name}"
    front = FRONT_MATTER.match(note.read_text(encoding="utf-8"))
    if front is None:
        return f"{note.name} is not a claims note"
    claims = tomllib.loads(front.group(1)).get("claims", [])
    status = next((c.get("status") for c in claims if c.get("n") == n), None)
    if status is None:
        return f"{note.name} has no claim {n}"
    return None if status == "current" else f"claim {n} is {status}"


def _section(note: Path, n: int) -> str | None:
    if not note.is_file():
        return f"no note {note.name}"
    heading = re.compile(rf"^## {n}\. ", re.MULTILINE)
    return None if heading.search(note.read_text(encoding="utf-8")) else f"no section {n}"


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        if value.startswith("rn:"):
            yield value
    elif isinstance(value, dict):
        for item in cast(dict[str, object], value).values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            yield from _strings(item)
