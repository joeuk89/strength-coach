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
from coach.core.draft_kinds.ledger import CHECK_IN
from coach.services.checkin_record import checkin_record


def run(call: InstanceCall) -> Outcome:
    path = str(call.args["draft"])
    data = read_draft(path)
    with open_instance_store(call.instance) as conn:
        result = checkin_record(
            conn, data, file=path, clock=call.clock, dry_run=on_dry_run(call.args)
        )
    summary: Json = {
        "check_in": result.check_in,
        "draft_hash": result.draft_hash,
        "tier": result.tier,
        "window": {
            "start": result.window_start.isoformat(),
            "end": result.window_end.isoformat(),
        },
        "ids": result.ids,
        "withdrawn": result.withdrawn,
        "superseded": result.superseded,
        "phase": {"opened": result.phase_opened, "closed": result.phase_closed},
    }
    return Outcome(marked(summary, dry_run=result.dry_run, no_op=result.no_op))


DECLARATION = Declaration(
    name="checkin record",
    summary=(
        "Record a check-in file: the Check-in row with its derived window, and every record "
        "the file carries stamped with it, in one transaction. The header is date, tier, read, "
        "readiness, and window_start on the instance's first check-in only; [phase] opens or "
        "closes the Phase; [[observation]] is reserved to this file. The same file again "
        "writes nothing; a changed file for the same date supersedes the row."
    ),
    writes="store",
    arguments=(Argument("draft", "path of the TOML check-in file", required=True), DRY_RUN),
    output={
        "type": "object",
        "properties": {
            "check_in": {"type": "string"},
            "draft_hash": {"type": "string"},
            "tier": {"enum": ["light", "deep"]},
            "window": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "format": "date"},
                    "end": {"type": "string", "format": "date"},
                },
                "required": ["start", "end"],
            },
            "ids": {
                "type": "object",
                "description": "ids written, by record kind; a retired Observation's id too",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "withdrawn": {"type": "array", "items": {"type": "string"}},
            "superseded": {
                "type": ["string", "null"],
                "description": "the row this one supersedes",
            },
            "phase": {
                "type": "object",
                "properties": {
                    "opened": {"type": ["string", "null"]},
                    "closed": {"type": ["string", "null"]},
                },
                "required": ["opened", "closed"],
            },
            **DRY_RUN_OUTPUT,
        },
        "required": [
            "check_in",
            "draft_hash",
            "tier",
            "window",
            "ids",
            "withdrawn",
            "superseded",
            "phase",
        ],
    },
    run=InInstance(run),
    draft=lambda: CHECK_IN,
    examples=(
        Example(
            ("checkin", "record", ".coach/drafts/2026-11-01-checkin.toml"),
            "Record a check-in file.",
        ),
        Example(
            ("checkin", "record", ".coach/drafts/2026-11-01-checkin.toml", "--dry-run"),
            "The check-in row and ids recording a check-in file would assign.",
        ),
    ),
)
