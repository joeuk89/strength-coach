from coach.cli import registry
from coach.cli.declaration import Argument, Call, Declaration, Example, Outcome
from coach.core.errors import Invalid


def run(call: Call) -> Outcome:
    name = call.args.get("verb")
    if not isinstance(name, str):
        return Outcome({"verbs": [d.describe() for d in registry.declarations()]})
    declaration = registry.find(name)
    if declaration is None:
        raise Invalid("invalid_argument", f"no verb {name!r}; `coach schema` lists them all")
    return Outcome(declaration.describe())


DECLARATION = Declaration(
    name="schema",
    summary="The verb declarations as JSON Schema: one verb, or all of them.",
    writes="none",
    needs_instance=False,
    arguments=(Argument("verb", "the leaf to describe, quoted when it has two words"),),
    output={
        "type": "object",
        "description": "one declaration, or {verbs: [declaration]} without a verb",
    },
    run=run,
    examples=(
        Example(("schema",), "Every verb's declaration."),
        Example(("schema", "status"), "The declaration of status."),
    ),
)
