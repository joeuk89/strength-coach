from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.drafts import read_draft
from coach.cli.hevy_key import api_key
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files
from coach.core.config import Units
from coach.core.flag import Flag
from coach.render.approval_prompt import approval_prompt
from coach.services.plan_apply import DryRun, apply, dry_run


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    instance = call.instance
    path = str(call.args["draft"])
    data = read_draft(path)
    if call.args.get("dry_run") is True:
        with closing(open_instance_store(instance)) as conn:
            found = dry_run(
                conn,
                data,
                file=path,
                config=instance.config,
                kits=read_kit_files(instance),
                clock=call.clock,
            )
        units = instance.config.athlete.units
        return Outcome(dry_run_result(found, units=units, full=call.full, last=call.last))
    expect = call.args.get("expect")
    client = None
    if instance.config.hevy is not None:
        key = api_key(call.env, instance.root / ".env")
        client = call.make_client(key, instance.audit_path, call.clock)
    with closing(open_instance_store(instance)) as conn:
        result = apply(
            conn,
            client,
            data,
            file=path,
            expect=expect if isinstance(expect, str) else None,
            config=instance.config,
            kits=read_kit_files(instance),
            clock=call.clock,
        )
    return Outcome(
        {
            "week_plan_id": result.week_plan_id,
            "write_plan_hash": result.write_plan_hash,
            "resumed": result.resumed,
            "outcomes": [o.to_json() for o in result.routines],
            "audit_lines": result.audit_lines,
        }
    )


def dry_run_result(found: DryRun, *, units: Units, full: bool, last: int) -> Json:
    """The dry run's result: the Write plan, its hash and the approval prompt. By default each
    flag is its key, severity and acknowledgement, since the prompt already carries its text."""
    checked = found.checked
    prompt = approval_prompt(checked, found.actions, found.write_plan_hash, units=units, full=full)
    flags = [flag.to_json() if full else _brief(flag) for flag in found.flags]
    kept = flags if full else flags[:last]
    draft = checked.draft
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


def _brief(flag: Flag) -> Json:
    return {
        "key": flag.key,
        "severity": flag.severity,
        "left": flag.left.to_json() if flag.left else None,
    }


DECLARATION = Declaration(
    name="plan apply",
    summary=(
        "The one Hevy write. With --dry-run: validate the plan Draft, report every violation "
        "and warning with the acknowledgements that leave them, list the Hevy actions (folders, "
        "routine update, create and retire, templates), and print the Write plan hash and the "
        "approval prompt. Any violation is exit 1. With --expect <hash>: write the WeekPlan "
        "approved, then push each routine, read it back and map it; a re-run resumes."
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
            "week_plan_id": {"type": "string"},
            "resumed": {"type": "boolean"},
            "outcomes": {"type": "array"},
            "audit_lines": {"type": "integer"},
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
        "required": ["write_plan_hash"],
    },
    run=run,
    examples=(
        Example(
            ("plan", "apply", ".coach/drafts/2026-11-01-plan.toml", "--dry-run"),
            "Validate the plan Draft and print its Write plan hash and approval prompt.",
        ),
        Example(
            ("plan", "apply", ".coach/drafts/2026-11-01-plan.toml", "--expect", "sha256:…"),
            "Push the approved Write plan to Hevy.",
        ),
    ),
)
