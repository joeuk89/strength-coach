import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from http.client import HTTPException
from typing import Protocol, cast

from coach.core.errors import Unreachable
from coach.core.report import REPO, Issue

BASE_URL = "https://api.github.com"
TOKEN_NAME = "COACH_GITHUB_TOKEN"
TIMEOUT_S = 30.0
ISSUES_PATH = f"/repos/{REPO}/issues"
# The only endpoint the engine may call: read open issues, file one. Nothing edits or closes.
ALLOWED = frozenset({("GET", ISSUES_PATH), ("POST", ISSUES_PATH)})
PAGE_SIZE = 100
MAX_PAGES = 10
CREATED = 201
TOKEN_REFUSED = frozenset({401, 403, 404})


class EndpointNotAllowed(Exception):
    """An engine bug: a request off the one allowed endpoint. Never sent."""


class Reply(Protocol):
    status: int

    def read(self) -> bytes: ...

    def close(self) -> None: ...


type Opener = Callable[[urllib.request.Request, float], Reply]
type Json = dict[str, object]


class _Failed(Exception):
    def __init__(self, status: int | None, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _urlopen(request: urllib.request.Request, timeout: float) -> Reply:
    return urllib.request.urlopen(request, timeout=timeout)


class GitHubApiClient:
    """The real `GitHubClient` over `urllib`. Reads need no token; filing does."""

    def __init__(self, token: str | None, *, opener: Opener = _urlopen) -> None:
        self._token = token
        self._opener = opener

    def open_issues(self) -> tuple[Issue, ...]:
        found: list[Issue] = []
        for page in range(1, MAX_PAGES + 1):
            query = {"state": "open", "per_page": PAGE_SIZE, "page": page}
            answer = self._expect_list(self.request("GET", ISSUES_PATH, query=query)[1])
            found.extend(_issue(item) for item in answer if "pull_request" not in item)
            if len(answer) < PAGE_SIZE:
                break
        return tuple(found)

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> Issue:
        payload: Json = {"title": title, "body": body, "labels": list(labels)}
        status, answer = self.request("POST", ISSUES_PATH, body=payload)
        if status != CREATED:
            raise self._unreachable(f"POST {ISSUES_PATH} answered {status}, not {CREATED}")
        if not isinstance(answer, dict):
            raise self._unreachable(f"POST {ISSUES_PATH} answered with no issue")
        return _issue(cast(Json, answer))

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | int] | None = None,
        body: Json | None = None,
    ) -> tuple[int, object]:
        if (method, path) not in ALLOWED:
            raise EndpointNotAllowed(f"{method} {path} is not the one allowed GitHub endpoint")
        try:
            return self._attempt(self._build(method, path, query, body))
        except _Failed as failure:
            detail = f"{method} {path} failed: {failure.detail}"
            raise self._unreachable(detail, failure.status) from None

    def _build(
        self, method: str, path: str, query: Mapping[str, str | int] | None, body: Json | None
    ) -> urllib.request.Request:
        url = BASE_URL + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {
            "accept": "application/vnd.github+json",
            "user-agent": "strength-coach",
            "x-github-api-version": "2022-11-28",
        }
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            headers["content-type"] = "application/json"
        return urllib.request.Request(url, data=data, method=method, headers=headers)

    def _attempt(self, request: urllib.request.Request) -> tuple[int, object]:
        try:
            reply = self._opener(request, TIMEOUT_S)
            try:
                raw = reply.read()
            finally:
                reply.close()
        except urllib.error.HTTPError as error:
            with error:
                said = error.read().decode("utf-8", errors="replace").strip()[:200]
            raise _Failed(
                error.code, f"HTTP {error.code}" + (f": {said}" if said else "")
            ) from None
        except (urllib.error.URLError, HTTPException, OSError) as error:
            reason = error.reason if isinstance(error, urllib.error.URLError) else error
            raise _Failed(
                None, f"could not reach GitHub ({reason or type(error).__name__})"
            ) from None
        try:
            return reply.status, json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            raise _Failed(reply.status, "GitHub answered with a payload that is not JSON") from None

    def _expect_list(self, answer: object) -> list[Json]:
        if not isinstance(answer, list) or not all(
            isinstance(item, dict) for item in cast(list[object], answer)
        ):
            raise self._unreachable(f"GET {ISSUES_PATH} answered with no list of issues")
        return cast(list[Json], answer)

    def _unreachable(self, detail: str, status: int | None = None) -> Unreachable:
        refused = status in TOKEN_REFUSED
        hint = f"; check {TOKEN_NAME}, the token that files issues" if refused else ""
        return Unreachable("github_unreachable", self._scrub(detail + hint))

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, f"[{TOKEN_NAME}]") if self._token else text


def _issue(item: Json) -> Issue:
    number, title, url, labels = (item.get(k) for k in ("number", "title", "html_url", "labels"))
    if (
        isinstance(number, int)
        and not isinstance(number, bool)
        and isinstance(title, str)
        and isinstance(url, str)
        and isinstance(labels, list)
    ):
        names = [
            cast(Json, label).get("name") if isinstance(label, dict) else label
            for label in cast(list[object], labels)
        ]
        return Issue(number, title, url, tuple(n for n in names if isinstance(n, str)))
    raise Unreachable("github_unreachable", "GitHub answered with an issue the client cannot read")
