from coach.cli.declaration import Argument, Declaration, Example, InInstance, InstanceCall, Outcome
from coach.cli.drafts import read_draft
from coach.cli.instance import open_instance_store
from coach.services.goal_adopt import goal_adopt

ID_OR_NULL = {"type": ["string", "null"]}


def run(call: InstanceCall) -> Outcome:
    path = str(call.args["draft"])
    data = read_draft(path)
    with open_instance_store(call.instance) as conn:
        result = goal_adopt(conn, data, file=path, clock=call.clock)
    return Outcome(
        {
            "draft_hash": result.draft_hash,
            "goal_id": result.goal_id,
            "kind": result.kind,
            "priority_lifts": list(result.priority_lifts),
            "milestones": list(result.milestones),
            "superseded": result.superseded,
            "phase": {"opened": result.phase_opened, "closed": result.phase_closed},
            "diff": result.diff,
        }
    )


DECLARATION = Declaration(
    name="goal adopt",
    summary=(
        "Record the athlete's Goal from a Draft, superseding the current one, and open or close "
        "the Phase in the same file. The same file again writes nothing and returns the same id."
    ),
    writes="store",
    arguments=(Argument("draft", "path of the TOML goal Draft", required=True),),
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
    examples=(
        Example(("goal", "adopt", ".coach/drafts/2026-10-30-goal.toml"), "Adopt a goal Draft."),
    ),
)
