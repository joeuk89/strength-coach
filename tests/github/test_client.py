import json
import urllib.error
from http.client import IncompleteRead
from typing import Any

import pytest
from support.recording_opener import RecordingOpener, Reply

from coach.core.errors import Unreachable
from coach.core.report import Issue
from coach.github.client import EndpointNotAllowed, GitHubApiClient

TOKEN = "github_pat_11AAAAAAA0secretsecretsecret"
ISSUES = "https://api.github.com/repos/joeuk89/strength-coach/issues"


def an_issue(number: int, title: str, *labels: str, **extra: Any) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/joeuk89/strength-coach/issues/{number}",
        "labels": [{"name": label} for label in labels],
        **extra,
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/repos/joeuk89/strength-coach/issues/1/comments"),
        ("PATCH", "/repos/joeuk89/strength-coach/issues/1"),
        ("DELETE", "/repos/joeuk89/strength-coach/issues"),
        ("POST", "/repos/someone/else/issues"),
        ("GET", "/user"),
        ("PUT", "/repos/joeuk89/strength-coach/issues"),
    ],
)
def test_a_request_off_the_allow_list_raises_before_the_opener_is_called(
    method: str, path: str
) -> None:
    opener = RecordingOpener()

    with pytest.raises(EndpointNotAllowed):
        GitHubApiClient(TOKEN, opener=opener).request(method, path)

    assert opener.sent == []


def test_create_issue_posts_title_body_and_labels_with_the_token_and_returns_the_issue() -> None:
    opener = RecordingOpener([Reply(201, an_issue(42, "Drops a set", "needs-triage", "bug"))])

    issue = GitHubApiClient(TOKEN, opener=opener).create_issue(
        "Drops a set", "the body", ("needs-triage", "bug")
    )

    assert issue == Issue(
        42,
        "Drops a set",
        "https://github.com/joeuk89/strength-coach/issues/42",
        ("needs-triage", "bug"),
    )
    [sent] = opener.sent
    assert (sent.method, sent.url) == ("POST", ISSUES)
    assert sent.body == {
        "title": "Drops a set",
        "body": "the body",
        "labels": ["needs-triage", "bug"],
    }
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    assert sent.headers["accept"] == "application/vnd.github+json"
    assert sent.headers["user-agent"]


def test_the_opener_gets_a_timeout() -> None:
    timeouts: list[float] = []
    opener = RecordingOpener([Reply(200, [])])

    def timed(request: Any, timeout: float) -> Any:
        timeouts.append(timeout)
        return opener(request, timeout)

    GitHubApiClient(None, opener=timed).open_issues()

    assert timeouts and 0 < timeouts[0] <= 60


def test_open_issues_reads_open_issues_page_by_page_and_drops_pull_requests() -> None:
    first = [an_issue(n, f"issue {n}", "bug") for n in range(1, 100)]
    first.append(an_issue(100, "a pull request", "bug", pull_request={"url": "x"}))
    opener = RecordingOpener([Reply(200, first), Reply(200, [an_issue(101, "last", "gap")])])

    issues = GitHubApiClient(None, opener=opener).open_issues()

    assert [i.number for i in issues] == [*range(1, 100), 101]
    assert [s.url for s in opener.sent] == [
        f"{ISSUES}?state=open&per_page=100&page=1",
        f"{ISSUES}?state=open&per_page=100&page=2",
    ]


def test_reading_with_no_token_sends_no_authorization() -> None:
    opener = RecordingOpener([Reply(200, [])])

    GitHubApiClient(None, opener=opener).open_issues()

    assert "authorization" not in opener.sent[0].headers


@pytest.mark.parametrize("status", [200, 202, 422, 500])
def test_a_post_answered_with_anything_but_201_is_github_unreachable(status: int) -> None:
    opener = RecordingOpener([Reply(status, an_issue(1, "t"))])

    with pytest.raises(Unreachable) as raised:
        GitHubApiClient(TOKEN, opener=opener).create_issue("t", "b", ("bug",))

    assert raised.value.code == "github_unreachable"
    assert str(status) in raised.value.message
    assert "COACH_GITHUB_TOKEN" not in raised.value.message


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_refused_token_names_the_token_in_the_hint(status: int) -> None:
    opener = RecordingOpener([Reply(status, {"message": "Bad credentials"})])

    with pytest.raises(Unreachable) as raised:
        GitHubApiClient(TOKEN, opener=opener).create_issue("t", "b", ("bug",))

    assert raised.value.code == "github_unreachable"
    assert "COACH_GITHUB_TOKEN" in raised.value.message


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("nodename nor servname provided"),
        TimeoutError("timed out"),
        IncompleteRead(b""),
        ConnectionResetError(54, "reset"),
    ],
)
def test_a_network_failure_is_github_unreachable(failure: Exception) -> None:
    opener = RecordingOpener([failure])

    with pytest.raises(Unreachable) as raised:
        GitHubApiClient(TOKEN, opener=opener).open_issues()

    assert raised.value.code == "github_unreachable"


def test_a_201_with_an_unreadable_payload_is_github_unreachable() -> None:
    opener = RecordingOpener([Reply(201, {"no": "number"})])

    with pytest.raises(Unreachable) as raised:
        GitHubApiClient(TOKEN, opener=opener).create_issue("t", "b", ("bug",))

    assert raised.value.code == "github_unreachable"


def test_the_token_is_scrubbed_from_every_error() -> None:
    echoed = {"message": f"token {TOKEN} is not allowed"}
    opener = RecordingOpener(
        [Reply(403, echoed), urllib.error.URLError(f"proxy said {TOKEN}"), Reply(200, echoed)]
    )
    client = GitHubApiClient(TOKEN, opener=opener)
    messages: list[str] = []
    for attempt in (
        lambda: client.create_issue("t", "b", ("bug",)),
        client.open_issues,
        client.open_issues,
    ):
        with pytest.raises(Unreachable) as raised:
            attempt()
        messages.append(json.dumps([raised.value.message, raised.value.details]))

    assert all(TOKEN not in m for m in messages)
    assert "[COACH_GITHUB_TOKEN]" in messages[0]
