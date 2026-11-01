import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from coach.cli.argv import find_leaf, parse_options
from coach.cli.declaration import Declaration
from coach.cli.hook.in_process import CoachRun
from coach.cli.hook.shell import CoachCall, Finding, HevyCall, Unreadable, scan
from coach.core.errors import Invalid
from coach.core.hevy_api import HEVY_HOST, WORKOUTS_PATH

# ADR 0006, "The hook": the modes where a human sees the prompt.
PROMPT_MODES = frozenset({"default", "acceptEdits", "plan", "auto"})
GATED_WRITES = frozenset({"hevy", "git"})
EXPECT = "--expect"
HASH_FIELD = "write_plan_hash"
PROMPT_FIELD = "prompt"
INTERNAL_ERROR = "internal_error"
FIELDS = "--fields"
BASH = "Bash"


@dataclass(frozen=True)
class Answer:
    decision: Literal["ask", "deny"]
    reason: str


def decide(
    hook_input: object, declarations: Sequence[Declaration], dry_run: CoachRun
) -> Answer | None:
    """The answer to one PreToolUse call, or None to leave it to the permission rules."""
    mode = _mode(hook_input)
    try:
        answers = _answers(hook_input, declarations, dry_run)
    except Exception as error:
        answers = [_unknown("this command", f"the hook failed: {type(error).__name__}: {error}")]
    if not answers:
        return None
    if mode not in PROMPT_MODES:
        answers = [_no_prompt(answer, mode) for answer in answers]
    denied = [a.reason for a in answers if a.decision == "deny"]
    if denied:
        return Answer("deny", "\n\n".join(denied))
    return Answer("ask", "\n\n".join(a.reason for a in answers))


def _mode(hook_input: object) -> object:
    return (
        cast(dict[str, object], hook_input).get("permission_mode")
        if isinstance(hook_input, dict)
        else None
    )


def _answers(
    hook_input: object, declarations: Sequence[Declaration], dry_run: CoachRun
) -> list[Answer]:
    if not isinstance(hook_input, dict):
        raise ValueError("the hook input is not a JSON object")
    fields = cast(dict[str, Any], hook_input)
    if fields.get("tool_name") != BASH:
        if not isinstance(fields.get("tool_name"), str):
            raise ValueError("the hook input names no tool")
        return []
    tool_input = fields.get("tool_input")
    command = (
        cast(dict[str, Any], tool_input).get("command") if isinstance(tool_input, dict) else None
    )
    if not isinstance(command, str):
        raise ValueError("the hook input has no Bash command")
    cwd = Path(fields.get("cwd") or Path.cwd())
    reviewed = (_review(found, declarations, dry_run) for found in scan(command, cwd))
    return [answer for answer in reviewed if answer is not None]


def _review(
    found: Finding, declarations: Sequence[Declaration], dry_run: CoachRun
) -> Answer | None:
    if isinstance(found, HevyCall):
        return _raw_hevy(found)
    if isinstance(found, Unreadable):
        return _unknown("this command", f"the hook cannot read it: {found.why}")
    return _coach(found, declarations, dry_run)


# ADR 0011: the client's allow-list has no workout write, so no method on /v1/workouts* passes.
def _raw_hevy(found: HevyCall) -> Answer:
    url = f"{HEVY_HOST}{found.path}"
    if found.path.startswith(WORKOUTS_PATH):
        return Answer(
            "deny",
            f"{url} is Hevy workout history, which no command may touch by any method; "
            "`coach import` is the one reader of it",
        )
    return Answer(
        "ask",
        f"This command calls the Hevy API directly ({url}), which skips the coach verbs' "
        "checks and the write audit. Allow it only if the athlete asked for this exact call.",
    )


def _coach(
    found: CoachCall, declarations: Sequence[Declaration], dry_run: CoachRun
) -> Answer | None:
    try:
        declaration, tokens = find_leaf(found.words, declarations)
    except Invalid:
        return None
    if declaration is None or declaration.writes not in GATED_WRITES:
        return None
    label = f"coach {declaration.name}"
    try:
        options = parse_options(declaration, tokens)
    except Invalid as error:
        return _unknown(label, f"its arguments do not parse: {error.message}")
    if options.help or options.args.get("dry_run") is True:
        return None
    if found.opaque:
        return _unknown(label, "a word in it is only known when the shell runs it")
    try:
        argv = [*declaration.name.split(), *_without_fields(tokens), "--dry-run"]
        envelope = dry_run(argv, found.cwd)
    except Exception as error:
        return _unknown(label, f"its dry run failed: {type(error).__name__}: {error}")
    if not envelope.get("ok"):
        error = envelope["error"]
        if error["code"] == INTERNAL_ERROR:
            return _unknown(label, f"its dry run failed: {error['message']}")
        return Answer("deny", f"{label} would be refused: {error['code']}: {error['message']}")
    result = envelope["result"]
    if any(a.name == EXPECT for a in declaration.arguments):
        stale = _stale_expect(label, options.args.get("expect"), result.get(HASH_FIELD))
        if stale is not None:
            return stale
    return Answer("ask", f"{label} writes. Its dry run:\n{_summary(result)}")


# ADR 0006, "The Write plan": the hook denies, rather than asks, on a missing or stale hash.
def _stale_expect(label: str, expected: object, current: object) -> Answer | None:
    if not isinstance(expected, str):
        return Answer(
            "deny",
            f"{label} needs {EXPECT} {current}, the Write plan hash of its own dry run; "
            "review the dry run and pass that hash",
        )
    if expected != current:
        return Answer(
            "deny",
            f"{label} {EXPECT} {expected} is stale: its dry run now gives {current}; "
            "review the dry run again and pass the new hash",
        )
    return None


def _without_fields(tokens: Sequence[str]) -> list[str]:
    """`tokens` without `--fields`, which would project the hash out of the dry run."""
    kept: list[str] = []
    skip_value = False
    for token in tokens:
        if skip_value:
            skip_value = False
        elif token == FIELDS:
            skip_value = True
        elif not token.startswith(f"{FIELDS}="):
            kept.append(token)
    return kept


def _summary(result: dict[str, Any]) -> str:
    prompt = result.get(PROMPT_FIELD)
    return prompt if isinstance(prompt, str) else json.dumps(result, indent=2)


def _unknown(label: str, why: str) -> Answer:
    return Answer(
        "ask",
        f"The hook cannot show what {label} would write ({why}). "
        "Allow it only if the athlete approved this exact write.",
    )


def _no_prompt(answer: Answer, mode: object) -> Answer:
    if answer.decision == "deny":
        return answer
    return Answer(
        "deny",
        f"{answer.reason}\n\nPermission mode {mode} shows no prompt, so nobody can say yes; "
        "run it in a mode that asks.",
    )
