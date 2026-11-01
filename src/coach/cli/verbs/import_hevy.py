from coach.cli.declaration import (
    Argument,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Outcome,
)
from coach.cli.instance import open_instance_store
from coach.cli.pull import PULL_PROPERTIES, REBUILT_PROPERTIES, pull, rebuilt_json


def run(call: InstanceCall) -> Outcome:
    rebuilt = rebuilt_json(call.rebuilt)
    with open_instance_store(call.instance) as conn:
        # The global --full also names the full pull here (verbs.md, `import [--full]`).
        pulled = pull(call, conn, call.instance, call.clock, full=call.full)
    if pulled is None:
        return Outcome({"skipped": True, "rebuilt": rebuilt})
    return Outcome({"rebuilt": rebuilt, **pulled.summary}, warnings=pulled.warnings)


DECLARATION = Declaration(
    name="import",
    summary=(
        "Pull Hevy into the store append-only: workouts with tombstones, weigh-ins, the "
        "routine and folder mirrors. Events since the last import; --full re-lists everything."
    ),
    writes="store",
    arguments=(
        Argument(
            "--full",
            "re-list every workout instead of the events since the last import",
            takes_value=False,
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "skipped": {"type": "boolean"},
            "rebuilt": {
                "type": ["object", "null"],
                "properties": REBUILT_PROPERTIES,
            },
            **PULL_PROPERTIES,
        },
        "required": ["rebuilt"],
    },
    run=InInstance(run),
    examples=(
        Example(("import",), "Pull the Hevy events since the last import."),
        Example(("import", "--full"), "Re-list the whole Hevy account."),
    ),
)
