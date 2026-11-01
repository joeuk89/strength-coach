from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.drafts import read_draft
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.services.program import AdoptResult, adopt


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    path = str(call.args["draft"])
    data = read_draft(path)
    position = call.args.get("position")
    with closing(open_instance_store(call.instance)) as conn:
        result = adopt(
            conn,
            data,
            file=path,
            config=call.instance.config,
            kits=read_kit_files(call.instance),
            clock=call.clock,
            dry_run=call.args.get("dry_run") is True,
            position=position if isinstance(position, str) else None,
        )
    return Outcome(_result(result))


def _result(result: AdoptResult) -> Json:
    summary: Json = {
        "version": result.version_id,
        "kind": result.kind,
        "position": result.position,
        "block": {"id": result.block, "reset": result.block_reset},
    }
    if result.dry_run:
        return summary | {
            "diff": result.diff.to_json(),
            "start_loads": [dict(load) for load in result.start_loads],
            "violations": list[Json](),
            "warnings": list[Json](),
            "no_op": result.no_op,
        }
    acknowledgements: list[Json] = [
        {"flag": entry.flag, "because": entry.because, "text": entry.text}
        for entry in result.acknowledgements
    ]
    return summary | {"acknowledgements": acknowledgements, "no_op": result.no_op}


DECLARATION = Declaration(
    name="program adopt",
    summary=(
        "Adopt a program Draft as the next Program version: validate it whole, fill the dose, "
        "deload and lifting minutes the emphasis owns, record it and open or continue the "
        "Block. The same file again is a no-op with the same version."
    ),
    writes="store",
    needs_instance=True,
    arguments=(
        Argument("draft", "path of the TOML program Draft", required=True),
        Argument(
            "--dry-run",
            "show the diff against the version in force, filled defaults marked, and each "
            "start load in athlete units with its Hevy kg; write nothing",
            takes_value=False,
        ),
        Argument("--position", "the rotation week a redesign starts at (default: the first)"),
    ),
    output={
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "kind": {"enum": ["amend", "redesign"]},
            "position": {"type": "string"},
            "block": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "reset": {"type": "boolean"}},
                "required": ["id", "reset"],
            },
            "acknowledgements": {"type": "array"},
            "no_op": {"type": "boolean"},
            "diff": {"type": "object", "description": "dry run only"},
            "start_loads": {"type": "array", "description": "dry run only"},
            "violations": {"type": "array", "description": "dry run only"},
            "warnings": {"type": "array", "description": "dry run only"},
        },
        "required": ["version", "kind", "position", "block", "no_op"],
    },
    run=run,
    examples=(
        Example(
            ("program", "adopt", ".coach/drafts/2026-10-30-program.toml", "--dry-run"),
            "Show what adopting a program Draft would record.",
        ),
    ),
)
