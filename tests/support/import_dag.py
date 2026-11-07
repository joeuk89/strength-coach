"""ADR 0019's import DAG, checked over the source tree with `ast`."""

import ast
import sys
from pathlib import Path

ALLOWED = {
    "core": {"core"},
    "store": {"core", "store"},
    "hevy": {"core", "hevy"},
    "github": {"core", "github"},
    "render": {"core", "render"},
    "services": {"core", "store", "hevy", "github", "render", "services"},
    "cli": {"core", "store", "hevy", "github", "render", "services", "cli"},
}
IO_LAYERS = {"store", "hevy", "github", "cli"}
IO_MODULES = {"sqlite3", "os", "pathlib", "urllib", "subprocess", "time"}
CLOCK_CALLS = {"now", "today", "utcnow"}
CLOCK_OWNERS = {"datetime", "date"}


def violations(src: Path, layer_only: str | None = None) -> list[str]:
    """Every forbidden edge under `src`, or under one layer of it."""
    found: list[str] = []
    for path in sorted((src / "coach").rglob("*.py")):
        module = ".".join(path.relative_to(src).with_suffix("").parts)
        is_package = path.name == "__init__.py"
        layer = _layer(module)
        if layer_only is not None and layer != layer_only:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        where = path.relative_to(src).as_posix()
        for node in ast.walk(tree):
            line = getattr(node, "lineno", 0)
            for name in _imported(node, module, is_package):
                problem = _import_problem(layer, name)
                if problem:
                    found.append(f"{where}:{line}: {problem}")
            if layer not in IO_LAYERS and _reads_the_clock(node):
                found.append(f"{where}:{line}: {layer} reads the system clock")
    return found


def _layer(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 2 and parts[1] in ALLOWED else "cli"


def _imported(node: ast.AST, module: str, is_package: bool) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    if node.level == 0:
        base = node.module or ""
    else:
        package = module.split(".") if is_package else module.split(".")[:-1]
        anchor = package[: len(package) - (node.level - 1)]
        base = ".".join([*anchor, *([node.module] if node.module else [])])
    if base == "coach":
        return [f"coach.{alias.name}" for alias in node.names]
    return [base]


def _import_problem(layer: str, name: str) -> str | None:
    parts = name.split(".")
    if parts[0] == "coach":
        target = parts[1] if len(parts) > 1 and parts[1] in ALLOWED else "cli"
        if target not in ALLOWED[layer]:
            return f"{layer} may not import {name}"
        return None
    if parts[0] not in sys.stdlib_module_names:
        return f"{name} is not in the standard library; the engine has no runtime dependencies"
    if layer not in IO_LAYERS and parts[0] in IO_MODULES:
        return f"{layer} may not import {name}"
    return None


def _reads_the_clock(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in CLOCK_CALLS:
        return False
    owner = node.func.value
    owner_name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", None)
    return owner_name in CLOCK_OWNERS
