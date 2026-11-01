import io
import json
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from email.message import Message
from urllib.error import HTTPError


@dataclass(frozen=True)
class Reply:
    status: int
    body: object = None
    read_error: Exception | None = None


@dataclass(frozen=True)
class Sent:
    method: str
    url: str
    headers: dict[str, str]
    body: object


class ScriptedResponse:
    def __init__(self, reply: Reply) -> None:
        self.status = reply.status
        self._bytes = _encoded(reply.body)
        self._read_error = reply.read_error

    def read(self) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        return self._bytes

    def close(self) -> None:
        pass


class RecordingOpener:
    """Answers each request from a script and refuses any request the script does not cover.

    A status of 400 or more is raised as urllib's `HTTPError`, as `urlopen` does.
    """

    def __init__(self, script: Iterable[Reply | Exception] = ()) -> None:
        self.script = list(script)
        self.sent: list[Sent] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> ScriptedResponse:
        data = request.data
        self.sent.append(
            Sent(
                method=request.get_method(),
                url=request.full_url,
                headers={k.lower(): v for k, v in request.header_items()},
                body=json.loads(data) if isinstance(data, bytes) else None,
            )
        )
        if not self.script:
            raise AssertionError("the recording opener refuses every unscripted connection")
        reply = self.script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply.status >= 400:
            body = io.BytesIO(_encoded(reply.body))
            raise HTTPError(request.full_url, reply.status, "error", Message(), body)
        return ScriptedResponse(reply)


@dataclass
class RecordingSleeper:
    slept: list[float] = field(default_factory=list[float])

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def _encoded(body: object) -> bytes:
    return b"" if body is None else json.dumps(body).encode()
