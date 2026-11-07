"""Every error code the engine source builds an error with, as a string literal."""

import ast
from pathlib import Path

ERRORS = frozenset({"CoachError", "Invalid", "Refused", "Unreachable", "Setup"})


def raised_with(src: Path, builders: frozenset[str] = ERRORS) -> dict[str, dict[str, list[str]]]:
    """Each literal code to the builders called with it, each to its `path:line` sites."""
    sites: dict[str, dict[str, list[str]]] = {}
    for path in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in builders
                and node.args
                and isinstance(code := node.args[0], ast.Constant)
                and isinstance(code.value, str)
            ):
                site = f"{path.relative_to(src)}:{node.lineno}"
                sites.setdefault(code.value, {}).setdefault(node.func.id, []).append(site)
    return sites


def raised_codes(src: Path) -> dict[str, list[str]]:
    """Each literal code to the `path:line` sites that build an error with it."""
    return {
        code: [site for found in builders.values() for site in found]
        for code, builders in raised_with(src).items()
    }
