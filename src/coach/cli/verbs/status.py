from contextlib import closing

from coach.cli.declaration import Call, Declaration, Example, Outcome
from coach.cli.instance import open_instance_store
from coach.services.status import status


def run(call: Call) -> Outcome:
    assert call.instance is not None
    with closing(open_instance_store(call.instance)) as conn:
        result = status(conn, engine_version=call.engine_version, pin=call.instance.pin)
    return Outcome(
        {
            "engine": {"version": result.engine_version, "pin": result.pin},
            "schema_version": result.schema_version,
        }
    )


DECLARATION = Declaration(
    name="status",
    summary="Where the instance stands: the engine version against its pin, the schema version.",
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
            "schema_version": {"type": "integer"},
        },
        "required": ["engine", "schema_version"],
    },
    run=run,
    examples=(Example(("status",), "Where the instance stands."),),
)
