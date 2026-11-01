import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from http.client import HTTPException
from pathlib import Path
from typing import Protocol, cast

from coach.core.clock import Clock
from coach.core.errors import Refused, Unreachable
from coach.core.mirror import (
    BodyMeasurement,
    ExerciseTemplate,
    Folder,
    Page,
    Routine,
    Workout,
    WorkoutEvent,
)
from coach.hevy import audit
from coach.hevy.key import KEY_NAME
from coach.hevy.parse import (
    parse_body_measurement_page,
    parse_exercise_template_page,
    parse_folder,
    parse_folder_page,
    parse_routine,
    parse_routine_page,
    parse_workout_events_page,
    parse_workout_page,
)
from coach.hevy.protocol import Payload, ReadBack, RoutineDiff, WriteContext
from coach.hevy.throttle import TokenBucket

BASE_URL = "https://api.hevyapp.com"
TIMEOUT_S = 30.0
RETRY_AFTER_429_S = 30
ATTEMPTS_ON_429 = 3

# ADR 0011, "The client": the only writes the engine may send. Hevy has no DELETE on any path.
ALLOWED_WRITES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"/v1/routines")),
    ("PUT", re.compile(r"/v1/routines/[^/?#]+")),
    ("POST", re.compile(r"/v1/routine_folders")),
    ("POST", re.compile(r"/v1/exercise_templates")),
)
_READ_PATH = re.compile(r"/v1/[A-Za-z0-9_/\-]+")


class EndpointNotAllowed(Exception):
    """An engine bug: a request off ADR 0011's allow-list. Never sent."""


class Reply(Protocol):
    status: int

    def read(self) -> bytes: ...

    def close(self) -> None: ...


type Opener = Callable[[urllib.request.Request, float], Reply]
type Sleeper = Callable[[float], None]


class _Failed(Exception):
    def __init__(self, status: int | None, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.attempts = 1


def _urlopen(request: urllib.request.Request, timeout: float) -> Reply:
    return urllib.request.urlopen(request, timeout=timeout)


def allowed(method: str, path: str) -> bool:
    if method == "GET":
        return _READ_PATH.fullmatch(path) is not None
    return any(m == method and p.fullmatch(path) for m, p in ALLOWED_WRITES)


class HevyApiClient:
    """The real `HevyClient` over `urllib`. Its constructor arguments are wiring, not seams."""

    def __init__(
        self,
        key: str,
        audit_path: Path,
        clock: Clock,
        *,
        opener: Opener = _urlopen,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self._key = key
        self._audit_path = audit_path
        self._clock = clock
        self._opener = opener
        self._sleeper = sleeper
        self._bucket = TokenBucket(clock, sleeper)

    def open_audit(self) -> None:
        self._append_audit([])

    def create_routine(self, body: Payload, context: WriteContext) -> Routine:
        answer = self.request("POST", "/v1/routines", body=body, context=context)
        return parse_routine(_written_routine(answer))

    def update_routine(self, routine_id: str, body: Payload, context: WriteContext) -> Routine:
        answer = self.request("PUT", _routine_path(routine_id), body=body, context=context)
        return parse_routine(_written_routine(answer))

    def create_folder(self, body: Payload, context: WriteContext) -> Folder:
        answer = self.request("POST", "/v1/routine_folders", body=body, context=context)
        return parse_folder(_field(answer, "routine_folder"))

    def create_exercise_template(self, body: Payload, context: WriteContext) -> str:
        answer = self.request("POST", "/v1/exercise_templates", body=body, context=context)
        template_id = answer if isinstance(answer, str | int) else _field(answer, "id")
        if isinstance(template_id, str | int) and not isinstance(template_id, bool) and template_id:
            return str(template_id)
        raise Unreachable("hevy_unreachable", "Hevy created an exercise template and sent no id")

    def workouts(self) -> tuple[Workout, ...]:
        return tuple(self._pages("/v1/workouts", parse_workout_page, 10))

    def workout_events(self, since: datetime.datetime) -> tuple[WorkoutEvent, ...]:
        query = {"since": since.isoformat()}
        return tuple(self._pages("/v1/workouts/events", parse_workout_events_page, 10, query))

    def routines(self) -> tuple[Routine, ...]:
        return tuple(self._pages("/v1/routines", parse_routine_page, 10))

    def routine(self, routine_id: str) -> Routine:
        return parse_routine(self.request("GET", _routine_path(routine_id)))

    def read_back(self, routine_id: str, context: WriteContext, diff: RoutineDiff) -> ReadBack:
        routine = self.routine(routine_id)
        found = diff(routine)
        self._append_audit([audit.verify_line(self._clock.now(), routine_id, context, found)])
        return ReadBack(routine=routine, diff=found)

    def folders(self) -> tuple[Folder, ...]:
        return tuple(self._pages("/v1/routine_folders", parse_folder_page, 10))

    def exercise_templates(self) -> tuple[ExerciseTemplate, ...]:
        return tuple(self._pages("/v1/exercise_templates", parse_exercise_template_page, 100))

    def body_measurements(self) -> tuple[BodyMeasurement, ...]:
        return tuple(self._pages("/v1/body_measurements", parse_body_measurement_page, 10))

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str | int] | None = None,
        body: Payload | None = None,
        context: WriteContext | None = None,
    ) -> object:
        """Send one request. A write needs a body and a context, and is audited."""
        if not allowed(method, path):
            raise EndpointNotAllowed(f"{method} {path} is not on the Hevy allow-list")
        if method == "GET":
            try:
                return self._send(method, path, query, None)[1]
            except _Failed as failure:
                raise self._unreachable(method, path, failure) from None
        if body is None or context is None:
            raise EndpointNotAllowed(f"{method} {path} needs a body and a WriteContext")
        self._append_audit([audit.request_line(self._clock.now(), method, path, body, context)])
        try:
            attempts, answer = self._send(method, path, query, body)
        except _Failed as failure:
            error = self._unreachable(method, path, failure)
            line = audit.response_line(
                self._clock.now(),
                method,
                path,
                body,
                attempts=failure.attempts,
                error=error.message,
            )
            self._append_audit([line])
            raise error from None
        line = audit.response_line(
            self._clock.now(), method, path, body, attempts=attempts, status=200
        )
        self._append_audit([line])
        return answer

    def _pages[T](
        self,
        path: str,
        parse: Callable[[object], Page[T]],
        page_size: int,
        query: Mapping[str, str | int] | None = None,
    ) -> Iterator[T]:
        number = 1
        while True:
            page = parse(
                self.request(
                    "GET", path, query={**(query or {}), "page": number, "pageSize": page_size}
                )
            )
            yield from page.items
            if number >= page.page_count:
                return
            number += 1

    def _send(
        self, method: str, path: str, query: Mapping[str, str | int] | None, body: Payload | None
    ) -> tuple[int, object]:
        request = self._build(method, path, query, body)
        attempts = 0
        while True:
            if body is not None:
                self._bucket.take()
            attempts += 1
            try:
                return attempts, self._attempt(request)
            except _Failed as failure:
                if failure.status == 429 and attempts < ATTEMPTS_ON_429:
                    self._sleeper(RETRY_AFTER_429_S)
                    continue
                failure.attempts = attempts
                raise

    def _unreachable(self, method: str, path: str, failure: _Failed) -> Unreachable:
        detail = f"{method} {path} failed after {failure.attempts} attempt(s): {failure.detail}"
        return Unreachable("hevy_unreachable", self._scrub(detail + _advice(failure.status)))

    def _build(
        self, method: str, path: str, query: Mapping[str, str | int] | None, body: Payload | None
    ) -> urllib.request.Request:
        url = BASE_URL + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {"api-key": self._key, "accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            headers["content-type"] = "application/json"
        return urllib.request.Request(url, data=data, method=method, headers=headers)

    def _attempt(self, request: urllib.request.Request) -> object:
        try:
            reply = self._opener(request, TIMEOUT_S)
        except urllib.error.HTTPError as error:
            with error:
                said = error.read().decode("utf-8", errors="replace").strip()[:200]
            raise _Failed(
                error.code, f"HTTP {error.code}" + (f": {said}" if said else "")
            ) from None
        except (urllib.error.URLError, HTTPException, OSError) as error:
            reason = error.reason if isinstance(error, urllib.error.URLError) else error
            raise _Failed(
                None, f"could not reach Hevy ({reason or type(error).__name__})"
            ) from None
        try:
            raw = reply.read()
        finally:
            reply.close()
        try:
            return json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            return raw.decode("utf-8", errors="replace").strip()

    def _append_audit(self, lines: list[audit.AuditLine]) -> None:
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8", newline="\n") as handle:
                for line in lines:
                    text = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
                    handle.write(self._scrub(text) + "\n")
        except OSError as error:
            raise Refused(
                "audit_unwritable",
                f"cannot open the Write audit {self._audit_path} for append: {error.strerror}",
            ) from None

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, f"[{KEY_NAME}]") if self._key else text


def _advice(status: int | None) -> str:
    if status in (401, 403):
        return f"; check {KEY_NAME} (the Hevy API needs Hevy Pro)"
    return ""


def _routine_path(routine_id: str) -> str:
    return f"/v1/routines/{urllib.parse.quote(routine_id, safe='')}"


def _field(answer: object, key: str) -> object:
    return cast(Payload, answer).get(key) if isinstance(answer, dict) else None


def _written_routine(answer: object) -> Payload:
    """Hevy wraps a written routine in `routine`, sometimes as a one-item list."""
    routine = _field(answer, "routine")
    if isinstance(routine, list) and len(cast(list[object], routine)) == 1:
        routine = cast(list[object], routine)[0]
    return {"routine": routine}
