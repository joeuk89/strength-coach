"""Literal tuples, lists and sets in the engine source made wholly of registry names: a second
copy of a list the registry already holds."""

import ast
from collections.abc import Collection
from pathlib import Path

REGISTRY = Path("coach", "core", "registries", "program.py")


def name_lists(src: Path, names: Collection[str]) -> list[str]:
    found: list[str] = []
    for path in sorted(src.rglob("*.py")):
        relative = path.relative_to(src)
        if relative == REGISTRY:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Tuple | ast.List | ast.Set):
                continue
            values = [e.value if isinstance(e, ast.Constant) else None for e in node.elts]
            if len(values) > 1 and all(isinstance(v, str) and v in names for v in values):
                found.append(f"{relative}:{node.lineno}")
    return found
