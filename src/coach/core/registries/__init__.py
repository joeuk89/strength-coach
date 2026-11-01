from coach.core.registries.ledger import REASONS
from coach.core.registries.registry import Entry, Registry

REGISTRIES: tuple[Registry[Entry], ...] = (REASONS,)


def find(name: str) -> Registry[Entry] | None:
    return next((r for r in REGISTRIES if r.name == name), None)
