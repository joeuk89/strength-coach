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
from coach.core.drafts.goal import GOAL
from coach.services.goal_adopt import goal_adopt

ID_OR_NULL = {"type": ["string", "null"]}


def run(call: InstanceCall) -> Outcome:
    path = str(call.args["draft"])
    data = read_draft(path)
    with open_instance_store(call.instance) as conn:
        result = goal_adopt(conn, data, file=path, clock=call.clock, dry_run=on_dry_run(call.args))
    summary: Json = {
        "draft_hash": result.draft_hash,
        "goal_id": result.goal_id,
        "kind": result.kind,
        "priority_lifts": list(result.priority_lifts),
        "milestones": list(result.milestones),
        "superseded": result.superseded,
        "phase": {"opened": result.phase_opened, "closed": result.phase_closed},
        "diff": result.diff,
    }
    return Outcome(marked(summary, dry_run=result.dry_run, no_op=result.no_op))


DECLARATION = Declaration(
    name="goal adopt",
    summary=(
        "Record the athlete's Goal from a Draft, superseding the current one, and open or close "
        "the Phase in the same file. The same file again writes nothing and returns the same id."
    ),
    writes="store",
    arguments=(Argument("draft", "path of the TOML goal Draft", required=True), DRY_RUN),
    output={
        "type": "object",
        "properties": {
            "draft_hash": {"type": "string"},
            "goal_id": {"type": "string"},
            "kind": {"enum": ["hypertrophy", "strength"]},
            "priority_lifts": {"type": "array", "items": {"type": "string"}},
            "milestones": {
                "type": "array",
                "description": "milestone ids, in Draft order",
                "items": {"type": "string"},
            },
            "superseded": {**ID_OR_NULL, "description": "the Goal this one superseded"},
            "phase": {
                "type": "object",
                "properties": {"opened": ID_OR_NULL, "closed": ID_OR_NULL},
                "required": ["opened", "closed"],
            },
            "diff": {
                "type": ["object", "null"],
                "description": (
                    "what changed from the superseded Goal, null for a first Goal: kind and "
                    "priority_lifts as {from, to}, milestones as {added, removed}, why as true"
                ),
            },
            **DRY_RUN_OUTPUT,
        },
        "required": [
            "draft_hash",
            "goal_id",
            "kind",
            "priority_lifts",
            "milestones",
            "superseded",
            "phase",
            "diff",
        ],
    },
    run=InInstance(run),
    draft=lambda: GOAL,
    examples=(
        Example(("goal", "adopt", ".coach/drafts/2026-10-30-goal.toml"), "Adopt a goal Draft."),
        Example(
            ("goal", "adopt", ".coach/drafts/2026-10-30-goal.toml", "--dry-run"),
            "The Goal and Phase ids adopting a goal Draft would record.",
        ),
    ),
)
