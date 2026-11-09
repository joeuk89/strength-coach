import datetime
import hashlib
from typing import cast

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
from coach.core.errors import Invalid
from coach.core.exercise_ladder import rung_shapes
from coach.core.program.form import ExerciseLadder
from coach.services.program import ShownLadder, ShowResult, show, show_draft


def run(call: InstanceCall) -> Outcome:
    out = call.args.get("out")
    as_draft = call.args.get("draft") is True
    if out is not None and not as_draft:
        raise Invalid("invalid_argument", "--out names where --draft writes; add --draft")
    week = _week(call.args.get("apply_plan"))
    if week is not None and not as_draft:
        raise Invalid("invalid_argument", "--apply-plan folds into the Draft; add --draft")
    with open_instance_store(call.instance) as conn:
        shown = show(conn, zone=call.clock.zone)
        drafted = show_draft(conn, apply_plan=week) if as_draft else None
    if drafted is None:
        return Outcome(_summary(shown, None if call.full else call.last))
    text = drafted.text
    path = write_engine_draft(
        call.instance.root,
        today=call.clock.today().isoformat(),
        kind="program",
        text=text,
        out=out if isinstance(out, str) else None,
    )
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    result: Json = {"version": shown.version_id, "path": path, "hash": digest}
    if week is not None:
        result["folded"] = [
            {"session": f.session_id, "exercise": f.exercise_id, "kind": f.kind}
            for f in drafted.folded
        ]
    return Outcome(result)


def _week(value: object) -> datetime.date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise Invalid("invalid_argument", f"--apply-plan {value!r} is not a date") from error


def _summary(shown: ShowResult, last: int | None) -> Json:
    sessions = [{"id": id_, "lines": lines} for id_, lines in shown.sessions]
    kept = sessions if last is None else sessions[:last]
    return {
        "version": shown.version_id,
        "kind": shown.kind,
        "emphasis": shown.emphasis,
        "adopted": shown.adopted,
        "because": shown.because,
        "sessions": kept,
        "count": len(sessions),
        "truncated": len(kept) < len(sessions),
        "ladders": [_ladder(ladder) for ladder in shown.ladders],
    }


def _ladder(shown: ShownLadder) -> Json:
    ladder = cast(ExerciseLadder, shown.line.ladder)
    return {
        "session": shown.session_id,
        "exercise": shown.line.exercise,
        "rungs": [
            {
                "rung": rung.rung,
                "exercise": rung.exercise,
                "cues": rung.cues,
                "sets": list(rung.set_groups),
                "criterion": rung.criterion,
                "standing": rung.standing,
            }
            for rung in rung_shapes(ladder, shown.standing)
        ],
    }


DECLARATION = Declaration(
    name="program show",
    summary=(
        "The Program version in force: number, kind, emphasis, adopted date, because, its "
        "sessions with line counts and every ladder rung by rung; with --draft, write it as a "
        "Draft to edit and return the path and hash; with --apply-plan, fold a week's line "
        "overrides into that Draft."
    ),
    writes="none",
    arguments=(
        Argument("--draft", "write the version in force as an amend Draft", takes_value=False),
        Argument("--out", "where --draft writes (default .coach/drafts/<date>-program.toml)"),
        Argument(
            "--apply-plan",
            "with --draft, fold the line overrides of the approved WeekPlan of the week "
            "starting on this Monday into the Draft",
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "kind": {"enum": ["amend", "redesign"]},
            "emphasis": {"enum": ["hypertrophy", "strength", "maintenance"]},
            "adopted": {"type": "string", "format": "date"},
            "because": {"type": "string"},
            "sessions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "lines": {"type": "integer"}},
                },
            },
            "count": {"type": "integer"},
            "truncated": {"type": "boolean"},
            "ladders": {
                "type": "array",
                "description": "every exercise_ladder line, the whole ladder",
                "items": {
                    "type": "object",
                    "properties": {
                        "session": {"type": "string"},
                        "exercise": {"type": "string"},
                        "rungs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "rung": {"type": "integer"},
                                    "exercise": {"type": "string"},
                                    "cues": {"type": ["string", "null"]},
                                    "sets": {"type": "array", "items": {"type": "object"}},
                                    "criterion": {
                                        "type": "object",
                                        "description": (
                                            "reps or duration_s, rpe_at_most and exposures, "
                                            "or manual alone"
                                        ),
                                    },
                                    "standing": {"type": "boolean"},
                                },
                            },
                        },
                    },
                },
            },
            "path": {"type": "string", "description": "with --draft"},
            "hash": {"type": "string", "description": "with --draft"},
            "folded": {
                "type": "array",
                "description": "with --apply-plan: the overrides folded in",
                "items": {
                    "type": "object",
                    "properties": {
                        "session": {"type": "string"},
                        "exercise": {"type": "string"},
                        "kind": {"type": "string"},
                    },
                },
            },
        },
        "required": ["version"],
    },
    run=InInstance(run),
    examples=(
        Example(("program", "show"), "The Program version in force."),
        Example(("program", "show", "--draft"), "Write the version in force as a Draft."),
        Example(
            ("program", "show", "--draft", "--apply-plan", "2026-11-02"),
            "Fold the week of 2 Nov 2026's swaps, pins, holds, restated sets and dropped lines "
            "into the Draft.",
        ),
    ),
)
