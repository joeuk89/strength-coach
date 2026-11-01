from coach.cli import registry
from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
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
        return Outcome({"verbs": [d.describe() for d in registry.declarations()]})
    declaration = registry.find(name)
    if declaration is None:
        raise Invalid("invalid_argument", f"no verb {name!r}; `coach schema` lists them all")
    return Outcome(declaration.describe())


def _registry(name: str, call: Call) -> Json:
    found = registries.find(name)
    if found is None:
        known = ", ".join(r.name for r in registries.REGISTRIES)
        raise Invalid("invalid_argument", f"no registry {name!r}; one of {known}")
    rows = found.rows()
    kept = rows if call.full else rows[: call.last]
    return {"registry": name, "rows": kept, "count": len(rows), "truncated": len(kept) < len(rows)}


DECLARATION = Declaration(
    name="schema",
    summary="The verb declarations as JSON Schema, or one registry as data.",
    writes="none",
    needs_instance=False,
    arguments=(
        Argument("verb", "the leaf to describe, quoted when it has two words"),
        Argument("--registry", "the registry to print instead, by name"),
    ),
    output={
        "type": "object",
        "description": "one declaration, {verbs: [declaration]} without a verb, "
        "or {registry, rows, count, truncated} with --registry",
    },
    run=run,
    examples=(
        Example(("schema",), "Every verb's declaration."),
        Example(("schema", "status"), "The declaration of status."),
        Example(("schema", "--registry", "flags"), "Every flag code with its citation."),
    ),
)
