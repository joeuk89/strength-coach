import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coach.cli.declaration import Argument, Call, Declaration, Example, Outcome, Writes
from coach.cli.hook.app import main
from coach.cli.hook.in_process import CoachRun

HASH = "wp-3f9a"


def _unused(call: Call) -> Outcome:
    raise AssertionError("the hook runs a dry run, never the verb")


def a_declaration(name: str, writes: Writes, arguments: tuple[Argument, ...] = ()) -> Declaration:
    return Declaration(
        name=name,
        summary=name,
        writes=writes,
        needs_instance=True,
        output={},
        run=_unused,
        arguments=arguments,
        examples=(Example((*name.split(),), name),),
    )


PLAN_APPLY = a_declaration(
    "plan apply",
    "hevy",
    (
        Argument("draft", "the plan Draft", required=True),
        Argument("--dry-run", "print the Write plan", takes_value=False),
        Argument("--expect", "the Write plan hash"),
    ),
)
PUBLISH = a_declaration(
    "publish", "git", (Argument("--dry-run", "what would be written", takes_value=False),)
)
STATUS = a_declaration("status", "none")
RECORD = a_declaration("record", "store", (Argument("draft", "the Draft", required=True),))
DECLARATIONS = (PLAN_APPLY, PUBLISH, STATUS, RECORD)


def clean_dry_run(**result: Any) -> CoachRun:
    def run(argv: Sequence[str], cwd: Path) -> dict[str, Any]:
        return {"ok": True, "result": {"write_plan_hash": HASH, **result}}

    return run


@dataclass(frozen=True)
class HookRun:
    code: int
    stdout: str
    dry_runs: list[tuple[list[str], Path]]

    @property
    def answer(self) -> Any:
        return json.loads(self.stdout) if self.stdout else None

    @property
    def decision(self) -> str | None:
        answer = self.answer
        return answer["hookSpecificOutput"]["permissionDecision"] if answer else None

    @property
    def reason(self) -> str:
        return self.answer["hookSpecificOutput"]["permissionDecisionReason"]


def a_bash_call(command: str, *, mode: str | None = "default", cwd: str = "/athlete") -> str:
    payload: dict[str, Any] = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": cwd,
    }
    if mode is not None:
        payload["permission_mode"] = mode
    return json.dumps(payload)


def run_hook(
    event: str,
    stdin: str,
    *,
    declarations: Sequence[Declaration] = DECLARATIONS,
    run_coach: CoachRun | None = None,
    env: dict[str, str] | None = None,
) -> HookRun:
    seen: list[tuple[list[str], Path]] = []
    inner = run_coach or clean_dry_run()

    def recording(argv: Sequence[str], cwd: Path) -> dict[str, Any]:
        seen.append((list(argv), cwd))
        return inner(argv, cwd)

    out = io.StringIO()
    code = main(
        [event],
        io.StringIO(stdin),
        env or {},
        out,
        io.StringIO(),
        declarations=lambda: tuple(declarations),
        run_coach=recording,
    )
    return HookRun(code, out.getvalue(), seen)
