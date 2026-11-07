from collections.abc import Iterable, Sequence

from coach.cli.declaration import MakeGitHub
from coach.core.errors import Unreachable
from coach.core.report import REPO, Issue


class FakeGitHub:
    """The in-memory `GitHubClient` every test injects in place of the real one."""

    def __init__(
        self,
        issues: Iterable[Issue] = (),
        *,
        reads_fail: bool = False,
        writes_fail: bool = False,
        next_number: int = 1,
    ) -> None:
        self.issues = list(issues)
        self.filed: list[Issue] = []
        self.bodies: list[str] = []
        self.tokens: list[str | None] = []
        self._reads_fail = reads_fail
        self._writes_fail = writes_fail
        self._next = next_number

    def factory(self) -> MakeGitHub:
        def make_github(token: str | None) -> FakeGitHub:
            self.tokens.append(token)
            return self

        return make_github

    def open_issues(self) -> tuple[Issue, ...]:
        if self._reads_fail:
            raise Unreachable("github_unreachable", "GET issues failed: could not reach GitHub")
        return tuple(self.issues)

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> Issue:
        if self._writes_fail:
            raise Unreachable("github_unreachable", "POST issues failed: HTTP 503")
        issue = Issue(
            self._next, title, f"https://github.com/{REPO}/issues/{self._next}", tuple(labels)
        )
        self._next += 1
        self.issues.append(issue)
        self.filed.append(issue)
        self.bodies.append(body)
        return issue


def an_open_issue(number: int, title: str, *labels: str) -> Issue:
    return Issue(number, title, f"https://github.com/{REPO}/issues/{number}", labels)
