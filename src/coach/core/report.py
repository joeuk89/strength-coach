"""A Report as the issue it files (docs/spec/voice.md, "Reporting"): the Draft parsed, the
footer the engine appends, the fixed labels, and the open issues that look like it."""

import re
import tomllib
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from coach.core.draft_fields import Fields, required
from coach.core.errors import Invalid
from coach.core.registries.errors import ERRORS

REPO = "joeuk89/strength-coach"
# An unconfirmed figure for GitHub's issue body limit, never checked against the live API.
BODY_LIMIT = 65_536
KINDS = ("bug", "gap")
TRIAGE = "needs-triage"
KIND_LABELS = {"bug": "bug", "gap": "enhancement"}
SIMILAR_LABELS = frozenset(KIND_LABELS.values())
SHARED_WORDS = 2
_STOPWORDS = (
    "a an and are as at be but by can do does for from has have how i in into is it its no not "
    "of on or so that the their there this to was what when where which while who why will with "
    "without"
)
STOPWORDS = frozenset(_STOPWORDS.split())
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Footer:
    """What the engine appends to every Report: who it was for and what it ran on."""

    athlete: str
    engine_version: str
    pin: str
    schema_version: int
    python: str
    platform: str


@dataclass(frozen=True)
class IssueDraft:
    title: str
    body: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    url: str
    labels: tuple[str, ...]


def issue_draft(data: bytes, *, verbs: Collection[str], footer: Footer) -> IssueDraft:
    """The issue a Report Draft files, its body as it will be sent, footer included."""
    fields = Fields(_document(data), "the report Draft")
    kind = required(fields.choice("kind", KINDS, required=True))
    title = required(fields.text("title", required=True))
    body = required(fields.text("body", required=True))
    verb = fields.choice("verb", tuple(sorted(verbs)))
    code = fields.term("code", ERRORS)
    fields.done(None)
    full = f"{body.rstrip()}\n\n{_footer(footer, verb, code)}"
    if len(full) > BODY_LIMIT:
        raise Invalid(
            "invalid_argument",
            f"the report body is {len(full)} characters with its footer; GitHub takes at most "
            f"{BODY_LIMIT}",
        )
    return IssueDraft(title=title, body=full, labels=(TRIAGE, KIND_LABELS[kind]))


def similar(title: str, issues: Iterable[Issue]) -> tuple[Issue, ...]:
    """The issues labelled bug or enhancement whose title shares enough words with `title`."""
    words = _words(title)
    return tuple(
        issue
        for issue in issues
        if SIMILAR_LABELS & set(issue.labels) and len(words & _words(issue.title)) >= SHARED_WORDS
    )


def athlete_name(profile: str | None, folder: str) -> str:
    """The profile's first heading, else the instance folder's name."""
    for line in (profile or "").splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return folder


def _document(data: bytes) -> dict[str, object]:
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Invalid("invalid_argument", f"the report Draft does not parse: {error}") from error


def _footer(footer: Footer, verb: str | None, code: str | None) -> str:
    lines = [
        "---",
        f"- Athlete: {footer.athlete}",
        f"- Engine: {footer.engine_version}, pin {footer.pin}, schema {footer.schema_version}",
        f"- Python: {footer.python} on {footer.platform}",
    ]
    if verb is not None:
        lines.append(f"- Verb: `{verb}`")
    if code is not None:
        lines.append(f"- Code: `{code}`")
    return "\n".join(lines) + "\n"


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower())) - STOPWORDS
