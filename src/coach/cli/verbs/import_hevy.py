from contextlib import closing
from dataclasses import asdict

from coach.cli.declaration import (
    Argument,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Json,
    Outcome,
)
from coach.cli.hevy_key import api_key
from coach.cli.instance import open_instance_store
from coach.services.hevy_import import ImportResult, import_hevy


def run(call: InstanceCall) -> Outcome:
    instance = call.instance
    rebuilt: Json | None = (
        None if call.rebuilt is None else {"schema_version": call.rebuilt.schema_version}
    )
    if instance.config.hevy is None:
        return Outcome({"skipped": True, "rebuilt": rebuilt})
    key = api_key(call.env, instance.root / ".env")
    client = call.make_client(key, instance.audit_path, call.clock)
    with closing(open_instance_store(instance)) as conn:
        # The global --full also names the full pull here (verbs.md, `import [--full]`).
        result = import_hevy(
            conn, client, call.clock, full=call.full, units=instance.config.athlete.units
        )
    return Outcome({"rebuilt": rebuilt, **_summary(result)}, warnings=result.warnings)


def _summary(result: ImportResult) -> Json:
    return {
        "kind": result.kind,
        "window": {"since": result.since, "until": result.at},
        "workouts": asdict(result.workouts),
        "weigh_ins": result.weigh_ins,
        "routines": result.routines,
        "folders": result.folders,
    }


_COUNT = {"type": "integer"}
_NULLABLE_TEXT = {"type": ["string", "null"]}

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
                "properties": {"schema_version": _COUNT},
            },
            "kind": {"enum": ["event", "full"]},
            "window": {
                "type": "object",
                "properties": {"since": _NULLABLE_TEXT, "until": {"type": "string"}},
            },
            "workouts": {
                "type": "object",
                "properties": {k: _COUNT for k in ("new", "versioned", "gone", "back")},
            },
            "weigh_ins": _COUNT,
            "routines": _COUNT,
            "folders": _COUNT,
        },
        "required": ["rebuilt"],
    },
    run=InInstance(run),
    examples=(
        Example(("import",), "Pull the Hevy events since the last import."),
        Example(("import", "--full"), "Re-list the whole Hevy account."),
    ),
)
