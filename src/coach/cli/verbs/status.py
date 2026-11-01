from contextlib import closing

from coach.cli.declaration import Call, Declaration, Example, Outcome
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.services.status import status


def run(call: Call) -> Outcome:
    assert call.instance is not None
    with closing(open_instance_store(call.instance)) as conn:
        result = status(
            conn,
            engine_version=call.engine_version,
            pin=call.instance.pin,
            hevy_on=call.instance.config.hevy is not None,
            kits=read_kit_files(call.instance),
        )
    return Outcome(
        {
            "engine": {"version": result.engine_version, "pin": result.pin},
            "hevy": {"on": result.hevy_on},
            "schema_version": result.schema_version,
            "kit": [
                {"location": kit.location, "kit": kit.kit, "tables": kit.tables}
                for kit in result.kit
            ],
            "program": (
                None
                if result.program is None
                else {
                    "version": result.program.version,
                    "kind": result.program.kind,
                    "emphasis": result.program.emphasis,
                    "adopted": result.program.adopted,
                }
            ),
        }
    )


DECLARATION = Declaration(
    name="status",
    summary=(
        "Where the instance stands: the engine version against its pin, Hevy on or off, "
        "the schema version, each plate-pool location's kit tables current or stale, "
        "the program version in force."
    ),
    writes="none",
    needs_instance=True,
    output={
        "type": "object",
        "properties": {
            "engine": {
                "type": "object",
                "properties": {"version": {"type": "string"}, "pin": {"type": "string"}},
                "required": ["version", "pin"],
            },
            "hevy": {
                "type": "object",
                "properties": {"on": {"type": "boolean"}},
                "required": ["on"],
            },
            "schema_version": {"type": "integer"},
            "kit": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "kit": {"type": "string"},
                        "tables": {"enum": ["current", "stale"]},
                    },
                    "required": ["location", "kit", "tables"],
                },
            },
            "program": {
                "description": "the Program version in force, or null before the first",
                "type": ["object", "null"],
                "properties": {
                    "version": {"type": "string"},
                    "kind": {"type": "string"},
                    "emphasis": {"type": "string"},
                    "adopted": {"type": "string"},
                },
            },
        },
        "required": ["engine", "hevy", "schema_version", "kit", "program"],
    },
    run=run,
    examples=(Example(("status",), "Where the instance stands."),),
)
