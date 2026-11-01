"""`coach-hook <event>`: the plugin's hooks, a second entry point beside `coach` (ADR 0019)."""

import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO, cast

from coach.cli import registry
from coach.cli.declaration import Declaration
from coach.cli.hook.gate import decide
from coach.cli.hook.in_process import CoachRun, run_in_process

NO_INSTANCE = "no_instance"


def main(
    argv: Sequence[str],
    stdin: TextIO,
    env: dict[str, str],
    stdout: TextIO,
    stderr: TextIO,
    *,
    declarations: Callable[[], Sequence[Declaration]] = registry.declarations,
    run_coach: CoachRun = run_in_process,
) -> int:
    event = argv[0] if argv else None
    hook_input = _read(stdin)
    if event == "session-start":
        output = _session_start(hook_input, run_coach)
    elif event == "pre-tool-use":
        output = _pre_tool_use(hook_input, declarations(), run_coach)
    else:
        stderr.write(f"coach-hook: unknown event {event!r}; one of session-start, pre-tool-use\n")
        return 1
    if output is not None:
        stdout.write(json.dumps({"hookSpecificOutput": output}) + "\n")
    return 0


def run() -> int:
    return main(sys.argv[1:], sys.stdin, dict(os.environ), sys.stdout, sys.stderr)


def _read(stdin: TextIO) -> object:
    try:
        return json.loads(stdin.read())
    except ValueError:
        return None


def _session_start(hook_input: object, run_coach: CoachRun) -> dict[str, Any] | None:
    fields = cast(dict[str, Any], hook_input) if isinstance(hook_input, dict) else {}
    status = run_coach(["status"], Path(fields.get("cwd") or Path.cwd()))
    if status.get("error", {}).get("code") == NO_INSTANCE:
        return None
    return {
        "hookEventName": "SessionStart",
        "additionalContext": json.dumps(status, separators=(",", ":")),
    }


def _pre_tool_use(
    hook_input: object, declarations: Sequence[Declaration], run_coach: CoachRun
) -> dict[str, Any] | None:
    answer = decide(hook_input, declarations, run_coach)
    if answer is None:
        return None
    return {
        "hookEventName": "PreToolUse",
        "permissionDecision": answer.decision,
        "permissionDecisionReason": answer.reason,
    }
