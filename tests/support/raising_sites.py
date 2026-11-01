"""Which registry flag codes the engine source never names outside the registry: a code with no
raising site. Some codes are raised through `Invalid`, `Message` or a helper rather than
`raise_flag`, so a string literal anywhere in the source counts as the site."""

import ast
from collections.abc import Iterable
from pathlib import Path

REGISTRY = Path("coach", "core", "registries", "flags.py")


def unraised(src: Path, codes: Iterable[str]) -> list[str]:
    named = {
        node.value
        for path in sorted(src.rglob("*.py"))
        if path.relative_to(src) != REGISTRY
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    return sorted(set(codes) - named)
