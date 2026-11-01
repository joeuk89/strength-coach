from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.drafts import read_draft
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.core.errors import Invalid
from coach.render.approval_prompt import approval_prompt
from coach.services.plan_apply import DryRun, dry_run


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    if call.args.get("dry_run") is not True:
        raise Invalid(
            "invalid_argument",
            "this engine build has no Hevy push yet; run plan apply with --dry-run",
        )
    path = str(call.args["draft"])
    data = read_draft(path)
    with closing(open_instance_store(call.instance)) as conn:
        found = dry_run(
            conn,
            data,
            file=path,
            config=call.instance.config,
            kits=read_kit_files(call.instance),
            clock=call.clock,
        )
    prompt = approval_prompt(
        found.checked,
        found.actions,
        found.write_plan_hash,
        units=call.instance.config.athlete.units,
        full=call.full,
    )
    return Outcome(_summary(found, prompt, None if call.full else call.last, full=call.full))


def _summary(found: DryRun, prompt: str, last: int | None, *, full: bool) -> Json:
    draft = found.checked.draft
    flags = [flag.to_json() if full else flag.to_summary() for flag in found.flags]
    kept = flags if last is None else flags[:last]
    return {
        "week": draft.week.isoformat(),
        "supersedes": draft.supersedes,
        "position": {"week": draft.position.week, "source": draft.position.source},
        **found.actions.to_json(),
        "flags": kept,
        "flag_count": len(flags),
        "flags_truncated": len(kept) < len(flags),
        "write_plan_hash": found.write_plan_hash,
        "prompt": prompt,
    }


DECLARATION = Declaration(
    name="plan apply",
    summary=(
        "The one Hevy write. With --dry-run: validate the plan Draft, report every violation "
        "and warning with the acknowledgements that leave them, list the Hevy actions (folders, "
        "routine update, create and retire, templates), and print the Write plan hash and the "
        "approval prompt. Any violation is exit 1."
    ),
    writes="hevy",
    needs_instance=True,
    arguments=(
        Argument("draft", "path of the TOML plan Draft", required=True),
        Argument(
            "--dry-run", "validate and print the Write plan; write nothing", takes_value=False
        ),
        Argument("--expect", "the Write plan hash of the dry run the athlete approved"),
    ),
    output={
        "type": "object",
        "properties": {
            "week": {"type": "string", "format": "date"},
            "supersedes": {"type": ["string", "null"]},
            "position": {"type": "object"},
            "folders_to_create": {"type": "array", "items": {"type": "string"}},
            "routines": {
                "type": "object",
                "properties": {
                    "update": {"type": "array"},
                    "create": {"type": "array"},
                    "retire": {"type": "array"},
                },
            },
            "templates_to_create": {"type": "array"},
            "flags": {"type": "array"},
            "flag_count": {"type": "integer"},
            "flags_truncated": {"type": "boolean"},
            "write_plan_hash": {"type": "string"},
            "prompt": {"type": "string"},
        },
        "required": ["week", "flags", "write_plan_hash", "prompt"],
    },
    run=run,
    examples=(
        Example(
            ("plan", "apply", ".coach/drafts/2026-11-01-plan.toml", "--dry-run"),
            "Validate the plan Draft and print its Write plan hash and approval prompt.",
        ),
    ),
)
