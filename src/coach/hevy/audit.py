"""The Write audit's three line kinds (ADR 0011, "Write audit"), shared by every `HevyClient`."""

import datetime
import hashlib
import json

from coach.hevy.protocol import Payload, WriteContext

type AuditLine = dict[str, object]


def body_digest(body: Payload) -> str:
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def request_line(
    at: datetime.datetime, method: str, path: str, body: Payload, context: WriteContext
) -> AuditLine:
    return {
        "kind": "request",
        "at": at.isoformat(),
        "method": method,
        "path": path,
        "routine_id": context.routine_id,
        "week_plan_id": context.week_plan_id,
        "write_plan_hash": context.write_plan_hash,
        "body": body,
        "body_sha256": body_digest(body),
    }


def response_line(
    at: datetime.datetime,
    method: str,
    path: str,
    body: Payload,
    *,
    attempts: int,
    status: int | None = None,
    error: str | None = None,
) -> AuditLine:
    line: AuditLine = {
        "kind": "response",
        "at": at.isoformat(),
        "method": method,
        "path": path,
        "body_sha256": body_digest(body),
    }
    if error is None:
        line["status"] = status
    else:
        line["error"] = error
    line["attempts"] = attempts
    return line


def verify_line(
    at: datetime.datetime, routine_id: str, context: WriteContext, diff: tuple[str, ...]
) -> AuditLine:
    return {
        "kind": "verify",
        "at": at.isoformat(),
        "routine_id": routine_id,
        "week_plan_id": context.week_plan_id,
        "write_plan_hash": context.write_plan_hash,
        "verified": not diff,
        "diff": list(diff),
    }
