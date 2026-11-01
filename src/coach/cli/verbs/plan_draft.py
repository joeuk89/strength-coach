import datetime

from coach.cli.declaration import (
    Argument,
    Declaration,
    Example,
    InInstance,
    InstanceCall,
    Json,
    Outcome,
)
from coach.cli.drafts import write_engine_draft
from coach.cli.instance import open_instance_store
from coach.cli.kit import read_kit_files, require_current_kit
from coach.core.draft_fields import draft_hash
from coach.core.errors import Invalid
from coach.core.plan_draft import PlanDraft
from coach.services.plan_draft import plan_draft


def run(call: InstanceCall) -> Outcome:
    require_current_kit(call.instance)
    out = call.args.get("out")
    with open_instance_store(call.instance) as conn:
        drafted = plan_draft(
            conn,
            config=call.instance.config,
            kits=read_kit_files(call.instance),
            clock=call.clock,
            week=_week(call.args.get("week")),
        )
    path = write_engine_draft(
        call.instance.root,
        today=call.clock.today().isoformat(),
        kind="plan",
        text=drafted.text,
        out=out if isinstance(out, str) else None,
    )
    digest = draft_hash(drafted.text.encode("utf-8"))
    return Outcome(_summary(drafted.draft, path, digest, None if call.full else call.last))


def _week(value: object) -> datetime.date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise Invalid("invalid_argument", f"--week {value!r} is not a date") from error


def _summary(draft: PlanDraft, path: str, digest: str, last: int | None) -> Json:
    flags: list[Json] = [
        {"key": f.key, "code": f.code, "severity": f.severity, "message": f.message}
        for f in draft.flags
    ]
    notes: list[Json] = [
        {"date": n.date.isoformat(), "text": n.text, "about": n.about} for n in draft.notes
    ]
    kept_flags = flags if last is None else flags[:last]
    kept_notes = notes if last is None else notes[-last:]
    return {
        "path": path,
        "hash": digest,
        "week": draft.week.isoformat(),
        "supersedes": draft.supersedes,
        "lines": draft.line_count,
        "position": {"week": draft.position.week, "source": draft.position.source},
        "flags": kept_flags,
        "flag_count": len(flags),
        "flags_truncated": len(kept_flags) < len(flags),
        "notes": kept_notes,
        "note_count": len(notes),
        "notes_truncated": len(kept_notes) < len(notes),
    }


DECLARATION = Declaration(
    name="plan draft",
    summary=(
        "Derive every line of the week's planned sessions from the history and write the plan "
        "Draft to edit, with the Athlete notes since the last approved WeekPlan. Returns the "
        "path, hash, week, the plan it supersedes, the line count, every violation and "
        "warning, the rotation position with its source and the notes."
    ),
    writes="none",
    arguments=(
        Argument(
            "--week",
            "the Monday of the week to plan (default: the first week from this one on with no "
            "approved WeekPlan)",
        ),
        Argument("--out", "where the Draft is written (default .coach/drafts/<date>-plan.toml)"),
    ),
    output={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "hash": {"type": "string"},
            "week": {"type": "string", "format": "date"},
            "supersedes": {"type": ["string", "null"]},
            "lines": {"type": "integer"},
            "position": {
                "type": "object",
                "properties": {
                    "week": {"type": "string"},
                    "source": {"enum": ["plan_in_force", "previous_plan", "program_adopt"]},
                },
                "required": ["week", "source"],
            },
            "flags": {"type": "array"},
            "flag_count": {"type": "integer"},
            "flags_truncated": {"type": "boolean"},
            "notes": {"type": "array"},
            "note_count": {"type": "integer"},
            "notes_truncated": {"type": "boolean"},
        },
        "required": ["path", "hash", "week", "supersedes", "lines", "position", "flags", "notes"],
    },
    run=InInstance(run),
    examples=(
        Example(("plan", "draft"), "Draft the next week with no approved plan."),
        Example(("plan", "draft", "--week", "2026-11-02"), "Draft the week starting 2 Nov 2026."),
    ),
)
