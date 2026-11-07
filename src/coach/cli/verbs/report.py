import platform

from coach.cli import registry
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
from coach.cli.drafts import read_draft
from coach.cli.keys import find_secret, github_token
from coach.core.draft_schema import DraftKind
from coach.core.drafts.report import report_kind
from coach.core.report import REPO, Footer, Issue, athlete_name, issue_draft
from coach.github.client import TOKEN_NAME
from coach.render.report_prompt import report_prompt
from coach.services.report import file, preview
from coach.store.chain import engine as engine_chain

PROFILE = "profile.md"
ISSUE_REF: Json = {
    "type": "object",
    "properties": {
        "number": {"type": "integer"},
        "title": {"type": "string"},
        "url": {"type": "string"},
    },
    "required": ["number", "title", "url"],
}


def run(call: InstanceCall) -> Outcome:
    root = call.instance.root
    issue = issue_draft(
        read_draft(str(call.args["draft"])),
        verbs=[d.name for d in registry.declarations()],
        footer=_footer(call),
    )
    dotenv = root / ".env"
    if on_dry_run(call.args):
        looked = preview(call.make_github(find_secret(TOKEN_NAME, call.env, dotenv)), issue)
        result: Json = {
            "dry_run": True,
            "repo": REPO,
            "title": issue.title,
            "labels": list(issue.labels),
            "body": issue.body,
            "similar": None if looked.similar is None else [_ref(i) for i in looked.similar],
            "prompt": report_prompt(REPO, issue),
        }
        return Outcome(result, looked.warnings)
    filed = file(call.make_github(github_token(call.env, dotenv)), issue)
    return Outcome({"number": filed.number, "url": filed.url, "labels": list(filed.labels)})


def _footer(call: InstanceCall) -> Footer:
    profile = call.instance.root / PROFILE
    return Footer(
        athlete=athlete_name(
            profile.read_text(encoding="utf-8") if profile.is_file() else None,
            call.instance.root.name,
        ),
        engine_version=call.engine_version,
        pin=call.instance.pin,
        schema_version=engine_chain().version,
        python=platform.python_version(),
        platform=platform.platform(),
    )


def _draft_kind() -> DraftKind:
    return report_kind(tuple(d.name for d in registry.declarations()))


def _ref(issue: Issue) -> Json:
    return {"number": issue.number, "title": issue.title, "url": issue.url}


DECLARATION = Declaration(
    name="report",
    summary="File a bug or a gap from a Draft as an issue on the engine's tracker, with the "
    "engine's footer and fixed labels; the dry run shows the issue as it will be sent and the "
    "open issues that look like it.",
    writes="github",
    arguments=(
        Argument("draft", "path of the TOML report Draft", required=True),
        Argument(
            "--dry-run",
            "show the repo, title, labels and the whole body as it will be sent, and similar "
            "open issues; file nothing",
            takes_value=False,
        ),
    ),
    output={
        "type": "object",
        "properties": {
            "number": {"type": "integer"},
            "url": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "dry_run": {"type": "boolean"},
            "repo": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string", "description": "the issue body as it will be sent"},
            "similar": {
                "type": ["array", "null"],
                "description": "open bug or enhancement issues sharing title words; null when "
                "GitHub cannot be read",
                "items": ISSUE_REF,
            },
            "prompt": {"type": "string"},
        },
        "required": ["labels"],
    },
    run=InInstance(run),
    over_budget=on_dry_run,
    draft=_draft_kind,
    examples=(
        Example(
            ("report", ".coach/drafts/2026-11-07-report.toml", "--dry-run"),
            "The issue as it will be sent, and similar open issues.",
        ),
        Example(("report", ".coach/drafts/2026-11-07-report.toml"), "File the issue."),
    ),
)
