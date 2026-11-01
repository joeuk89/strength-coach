"""Every error code the engine source builds an error with, as a string literal."""

import ast
from pathlib import Path

ERRORS = frozenset({"CoachError", "Invalid", "Refused", "Unreachable", "Setup"})


def raised_codes(src: Path) -> dict[str, list[str]]:
    """Each literal code to the `path:line` sites that build an error with it."""
    sites: dict[str, list[str]] = {}
    for path in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ERRORS
                and node.args
                and isinstance(code := node.args[0], ast.Constant)
                and isinstance(code.value, str)
            ):
                site = f"{path.relative_to(src)}:{node.lineno}"
                sites.setdefault(code.value, []).append(site)
    return sites
