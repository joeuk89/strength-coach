from dataclasses import dataclass

from coach.core.errors import Unreachable
from coach.core.message import Message
from coach.core.report import Issue, IssueDraft, similar
from coach.github.protocol import GitHubClient


@dataclass(frozen=True)
class Preview:
    """The dry run's look at the tracker: `similar` is None when GitHub could not be read."""

    similar: tuple[Issue, ...] | None
    warnings: tuple[Message, ...] = ()


def preview(client: GitHubClient, issue: IssueDraft) -> Preview:
    try:
        return Preview(similar(issue.title, client.open_issues()))
    except Unreachable as error:
        warning = Message(error.code, f"similar issues were not checked: {error.message}")
        return Preview(None, (warning,))


def file(client: GitHubClient, issue: IssueDraft) -> Issue:
    return client.create_issue(issue.title, issue.body, issue.labels)
