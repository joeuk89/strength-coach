import hashlib
from contextlib import closing

from coach.cli.declaration import Argument, Call, Declaration, Example, Json, Outcome
from coach.cli.drafts import write_engine_draft
from coach.cli.instance import open_instance_store
from coach.core.errors import Invalid
from coach.services.program import ShowResult, show, show_draft


def run(call: Call) -> Outcome:
    assert call.instance is not None and call.clock is not None
    out = call.args.get("out")
    as_draft = call.args.get("draft") is True
    if out is not None and not as_draft:
        raise Invalid("invalid_argument", "--out names where --draft writes; add --draft")
    with closing(open_instance_store(call.instance)) as conn:
        shown = show(conn)
        text = show_draft(conn) if as_draft else None
    if text is None:
        return Outcome(_summary(shown, None if call.full else call.last))
    path = write_engine_draft(
        call.instance.root,
        today=call.clock.today().isoformat(),
        kind="program",
        text=text,
        out=out if isinstance(out, str) else None,
    )
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Outcome({"version": shown.version_id, "path": path, "hash": digest})


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
    }


DECLARATION = Declaration(
    name="program show",
    summary=(
        "The Program version in force: number, kind, emphasis, adopted date, because and its "
        "sessions with line counts; with --draft, write it as a Draft to edit and return the "
        "path and hash."
    ),
    writes="none",
    needs_instance=True,
    arguments=(
        Argument("--draft", "write the version in force as an amend Draft", takes_value=False),
        Argument("--out", "where --draft writes (default .coach/drafts/<date>-program.toml)"),
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
            "path": {"type": "string", "description": "with --draft"},
            "hash": {"type": "string", "description": "with --draft"},
        },
        "required": ["version"],
    },
    run=run,
    examples=(
        Example(("program", "show"), "The Program version in force."),
        Example(("program", "show", "--draft"), "Write the version in force as a Draft."),
    ),
)
