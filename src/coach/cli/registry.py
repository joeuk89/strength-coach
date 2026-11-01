import importlib
import pkgutil
from functools import cache

from coach.cli import verbs
from coach.cli.declaration import Declaration


@cache
def declarations() -> tuple[Declaration, ...]:
    """Every leaf, found as the `DECLARATION` of each module under `coach.cli.verbs`."""
    found: list[Declaration] = []
    for module_info in pkgutil.iter_modules(verbs.__path__):
        module = importlib.import_module(f"{verbs.__name__}.{module_info.name}")
        declaration = getattr(module, "DECLARATION", None)
        if isinstance(declaration, Declaration):
            found.append(declaration)
    return tuple(sorted(found, key=lambda d: d.name))


def find(name: str) -> Declaration | None:
    return next((d for d in declarations() if d.name == name), None)
