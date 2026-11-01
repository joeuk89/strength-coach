from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Outcome
from coach.cli.drafts import read_draft
from coach.cli.instance import open_instance_store
from coach.services.record import record


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    path = str(call.args["draft"])
    data = read_draft(path)
    with closing(open_instance_store(call.instance)) as conn:
        result = record(conn, data, file=path, clock=call.clock)
    return Outcome(
        {"draft_hash": result.draft_hash, "ids": result.ids, "withdrawn": result.withdrawn}
    )


DECLARATION = Declaration(
    name="record",
    summary=(
        "Write a ledger Draft outside a check-in: any mix of record kinds, one array of tables "
        "per kind. The same file again writes nothing and returns the same ids."
    ),
    writes="store",
    needs_instance=True,
    arguments=(Argument("draft", "path of the TOML ledger Draft", required=True),),
    output={
        "type": "object",
        "properties": {
            "draft_hash": {"type": "string"},
            "ids": {
                "type": "object",
                "description": "ids written, by record kind",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "withdrawn": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["draft_hash", "ids", "withdrawn"],
    },
    run=run,
    examples=(
        Example(("record", ".coach/drafts/2026-10-30-record.toml"), "Record a ledger Draft."),
    ),
)
