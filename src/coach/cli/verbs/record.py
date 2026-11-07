from coach.cli.declaration import (
    Argument,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Json,
    Outcome,
    on_dry_run,
)
from coach.cli.drafts import DRY_RUN, DRY_RUN_OUTPUT, marked, read_draft
from coach.cli.instance import open_instance_store
from coach.core.drafts.ledger import RECORD
from coach.services.record import record


def run(call: InstanceCall) -> Outcome:
    path = str(call.args["draft"])
    data = read_draft(path)
    with open_instance_store(call.instance) as conn:
        result = record(conn, data, file=path, clock=call.clock, dry_run=on_dry_run(call.args))
    summary: Json = {
        "draft_hash": result.draft_hash,
        "ids": result.ids,
        "withdrawn": result.withdrawn,
    }
    return Outcome(marked(summary, dry_run=result.dry_run, no_op=result.no_op))


DECLARATION = Declaration(
    name="record",
    summary=(
        "Write a ledger Draft outside a check-in: any mix of record kinds, one array of tables "
        "per kind. The same file again writes nothing and returns the same ids."
    ),
    writes="store",
    arguments=(Argument("draft", "path of the TOML ledger Draft", required=True), DRY_RUN),
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
            **DRY_RUN_OUTPUT,
        },
        "required": ["draft_hash", "ids", "withdrawn"],
    },
    run=InInstance(run),
    draft=lambda: RECORD,
    examples=(
        Example(("record", ".coach/drafts/2026-10-30-record.toml"), "Record a ledger Draft."),
        Example(
            ("record", ".coach/drafts/2026-10-30-record.toml", "--dry-run"),
            "The ids recording a ledger Draft would assign.",
        ),
    ),
)
