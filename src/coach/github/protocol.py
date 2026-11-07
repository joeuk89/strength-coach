from collections.abc import Sequence
from typing import Protocol

from coach.core.report import Issue


class GitHubClient(Protocol):
    """The one seam to GitHub: read the open issues, and file one."""

    def open_issues(self) -> tuple[Issue, ...]: ...

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> Issue: ...
