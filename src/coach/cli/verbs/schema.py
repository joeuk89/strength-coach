from collections.abc import Sequence

from coach.cli import registry
from coach.cli.declaration import (
    Argument,
    Call,
    Declaration,
    Example,
    Json,
    Outcome,
    without_verb_or_registry,
)
from coach.core import registries
from coach.core.errors import Invalid


def run(call: Call) -> Outcome:
    name = call.args.get("verb")
    registry_name = call.args.get("registry")
    if isinstance(registry_name, str):
        if isinstance(name, str):
            raise Invalid("invalid_argument", "give a verb or --registry, not both")
        return Outcome(_registry(registry_name, call))
    if not isinstance(name, str):
        return Outcome(_every_verb())
    declaration = registry.find(name)
    if declaration is None:
        raise Invalid("invalid_argument", f"no verb {name!r}; `coach schema` lists them all")
    return Outcome(declaration.describe())


def _every_verb() -> Json:
    rows = [d.describe() for d in registry.declarations()]
    return {
        "rows": rows,
        "count": len(rows),
        "truncated": False,
        "registries": [r.name for r in registries.REGISTRIES],
    }


def _registry(name: str, call: Call) -> Json:
    found = registries.find(name)
    if found is None:
        known = ", ".join(r.name for r in registries.REGISTRIES)
        raise Invalid("invalid_argument", f"no registry {name!r}; one of {known}")
    return {"registry": name, **_rows(found.rows(), call)}


def _rows(rows: Sequence[Json], call: Call) -> Json:
    kept = list(rows) if call.full else list(rows[: call.last])
    return {"rows": kept, "count": len(rows), "truncated": len(kept) < len(rows)}


DECLARATION = Declaration(
    name="schema",
    summary="The verb declarations as JSON Schema, or one registry as data.",
    writes="none",
    arguments=(
        Argument("verb", "the leaf to describe, quoted when it has two words"),
        Argument("--registry", "the registry to print instead, by name"),
    ),
    output={
        "type": "object",
        "description": "one declaration with a verb; {rows: [declaration], count, truncated, "
        "registries} without one, never cut; {registry, rows, count, truncated} with --registry",
        "properties": {
            "registry": {"type": "string", "description": "with --registry"},
            "rows": {"type": "array", "items": {"type": "object"}},
            "count": {"type": "integer"},
            "truncated": {"type": "boolean"},
            "registries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "without a verb: every name --registry takes",
            },
        },
    },
    run=run,
    over_budget=without_verb_or_registry,
    examples=(
        Example(("schema",), "Every verb's declaration and the registry names."),
        Example(("schema", "status"), "The declaration of status."),
        Example(("schema", "--registry", "flags"), "Every flag code with its citation."),
    ),
)
