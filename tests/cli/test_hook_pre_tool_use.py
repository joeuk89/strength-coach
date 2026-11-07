import json
from pathlib import Path
from typing import Any

import pytest
from support.hook import HASH, a_bash_call, clean_dry_run, run_hook

from coach.cli.verbs.report import DECLARATION as REPORT

EVERY_MODE = ["default", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk", None]


def test_plan_apply_with_a_current_expect_asks_with_the_dry_run_summary_in_default_mode() -> None:
    run = run_hook("pre-tool-use", a_bash_call(f"coach plan apply x.toml --expect {HASH}"))

    assert run.code == 0
    assert run.decision == "ask"
    assert HASH in run.reason
    assert run.dry_runs[0][0] == ["plan", "apply", "x.toml", "--expect", HASH, "--dry-run"]


def test_plan_apply_with_a_current_expect_is_denied_in_bypass_permissions_mode() -> None:
    run = run_hook(
        "pre-tool-use",
        a_bash_call(f"coach plan apply x.toml --expect {HASH}", mode="bypassPermissions"),
    )

    assert run.decision == "deny"
    assert "bypassPermissions" in run.reason


STALE_APPLY = "coach plan apply x.toml --expect wp-old"


@pytest.mark.parametrize(
    "command",
    [
        STALE_APPLY,
        f"if true; then {STALE_APPLY}; fi",
        f"nice {STALE_APPLY}",
        f"timeout 5 {STALE_APPLY}",
        f"sudo -u me {STALE_APPLY}",
        f"{{ {STALE_APPLY}; }}",
    ],
)
@pytest.mark.parametrize("mode", EVERY_MODE)
def test_a_stale_expect_is_denied_in_every_mode(command: str, mode: str | None) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command, mode=mode))

    assert run.decision == "deny"
    assert "wp-old" in run.reason
    assert HASH in run.reason


@pytest.mark.parametrize("mode", EVERY_MODE)
def test_a_missing_expect_is_denied_in_every_mode(mode: str | None) -> None:
    run = run_hook("pre-tool-use", a_bash_call("coach plan apply x.toml", mode=mode))

    assert run.decision == "deny"
    assert "--expect" in run.reason


def test_the_dry_run_prompt_is_the_summary_shown_verbatim() -> None:
    prompt = "Week 2026-11-02, position 3\nbench_press 3 x 8 @ 80 kg (+2.5)\nHash wp-3f9a"
    run = run_hook(
        "pre-tool-use",
        a_bash_call(f"coach plan apply x.toml --expect {HASH}"),
        run_coach=clean_dry_run(prompt=prompt),
    )

    assert prompt in run.reason


def test_coach_report_asks_with_its_dry_run_prompt_whole_however_long() -> None:
    prompt = "Report to joeuk89/strength-coach\n" + "".join(f"line {n}\n" for n in range(300))
    run = run_hook(
        "pre-tool-use",
        a_bash_call("coach report .coach/drafts/report.toml"),
        declarations=[REPORT],
        run_coach=clean_dry_run(prompt=prompt),
    )

    assert run.decision == "ask"
    assert prompt in run.reason
    assert run.dry_runs[0][0] == ["report", ".coach/drafts/report.toml", "--dry-run"]


def test_a_dry_run_without_a_prompt_is_shown_as_its_result() -> None:
    run = run_hook(
        "pre-tool-use",
        a_bash_call("coach publish"),
        run_coach=clean_dry_run(files=["pages/week.md"]),
    )

    assert run.decision == "ask"
    assert '"pages/week.md"' in run.reason


def test_a_refusing_dry_run_is_denied_with_its_reason_in_default_mode() -> None:
    def refusing(argv: Any, cwd: Path) -> dict[str, Any]:
        return {"ok": False, "error": {"code": "no_instance", "message": "no coach.toml here"}}

    run = run_hook("pre-tool-use", a_bash_call("coach publish"), run_coach=refusing)

    assert run.decision == "deny"
    assert "no_instance" in run.reason
    assert "no coach.toml here" in run.reason


def throwing(argv: Any, cwd: Path) -> dict[str, Any]:
    raise RuntimeError("store locked")


@pytest.mark.parametrize("mode", ["default", "acceptEdits", "plan", "auto"])
def test_a_throwing_dry_run_asks_with_the_reason_where_a_prompt_exists(mode: str) -> None:
    run = run_hook(
        "pre-tool-use",
        a_bash_call(f"coach plan apply x.toml --expect {HASH}", mode=mode),
        run_coach=throwing,
    )

    assert run.decision == "ask"
    assert "store locked" in run.reason


@pytest.mark.parametrize("mode", ["dontAsk", "bypassPermissions", "yolo", None])
def test_a_throwing_dry_run_is_denied_where_no_prompt_exists(mode: str | None) -> None:
    run = run_hook("pre-tool-use", a_bash_call("coach publish", mode=mode), run_coach=throwing)

    assert run.decision == "deny"
    assert "store locked" in run.reason


def test_an_internal_error_in_the_dry_run_counts_as_throwing() -> None:
    def crashing(argv: Any, cwd: Path) -> dict[str, Any]:
        return {"ok": False, "error": {"code": "internal_error", "message": "KeyError: 'x'"}}

    run = run_hook("pre-tool-use", a_bash_call("coach publish"), run_coach=crashing)

    assert run.decision == "ask"
    assert "KeyError" in run.reason


@pytest.mark.parametrize(
    "command",
    [
        "coach plan apply x.toml --dry-run",
        "coach publish --help",
        "coach status",
        "coach record ledger.toml",
        "coach sync",
        "ls -la",
        "git commit -m 'coach publish'",
    ],
)
def test_a_command_that_writes_nothing_gated_gets_no_answer(command: str) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command))

    assert run.code == 0
    assert run.stdout == ""
    assert run.dry_runs == []


@pytest.mark.parametrize(
    "command",
    [
        "curl https://api.hevyapp.com/v1/workouts",
        "curl -X GET https://api.hevyapp.com/v1/workouts",
        "curl -X POST -d '{}' https://api.hevyapp.com/v1/workouts",
        "curl --request DELETE 'https://api.hevyapp.com/v1/workouts/abc'",
        "curl -H 'api-key: k' 'https://api.hevyapp.com/v1/workouts?page=1'",
        "curl https://api.hevyapp.com/v1/workouts/events",
        "wget -qO- https://api.hevyapp.com/v1/workouts/count",
        "http PUT api.hevyapp.com/v1/workouts/abc title=x",
        "python3 -c \"import urllib.request as u; u.urlopen('https://api.hevyapp.com/v1/workouts')\"",
        "curl https://API.HEVYAPP.COM/v1/workouts -X DELETE",
        "curl https://Api.HevyApp.com/v1/workouts",
        "curl https://api.hevyapp.com./v1/workouts",
        "curl https://api.hevyapp.com/v1/workouts%2Fabc",
        "curl https://api.hevyapp.com/v1/%77orkouts",
        "curl https://api.hevyapp.com/v1/workoutsX",
        "timeout 5 curl https://api.hevyapp.com/v1/workouts",
        "if true; then curl -X DELETE https://api.hevyapp.com/v1/workouts/abc; fi",
        "python3 - <<'EOF'\nimport urllib.request as u\n"
        "u.urlopen(u.Request('https://api.hevyapp.com/v1/workouts/abc', method='DELETE'))\nEOF",
        "node <<EOF\nfetch('https://api.hevyapp.com/v1/workouts/abc',{method:'DELETE'})\nEOF",
        "cat > x.py <<'EOF'\nimport urllib.request as u\n"
        "u.urlopen('https://api.hevyapp.com/v1/workouts')\nEOF\npython3 x.py",
        "python3 - <<'EOF'\n# don't log the key\n"
        "import urllib.request as u; u.urlopen('https://api.hevyapp.com/v1/workouts')\nEOF",
        'curl https://api.hevyapp.com/v1/work"outs"',
        "curl 'https://api.hevyapp.com/v1/'workouts",
        "curl https://api.hevyapp.com/v1/work\\outs",
        "curl 'https://api.hevyapp.com/v1/{workouts,routines}'",
        "curl https://api.hevyapp.com/v1/[w]orkouts",
        "curl 'https://api.hevyapp.com/v1/*'",
        "X=outs; curl -X DELETE https://api.hevyapp.com/v1/work$X/abc",
        'curl -X DELETE "https://api.hevyapp.com/v1/$(echo workouts)/abc"',
        "P=/v1/workouts/abc; curl -X DELETE https://api.hevyapp.com$P",
        "curl -X DELETE https://api.hevyapp.com/v1/`echo workouts`/abc",
    ],
)
@pytest.mark.parametrize("mode", EVERY_MODE)
def test_any_method_on_hevy_workouts_is_denied(command: str, mode: str | None) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command, mode=mode))

    assert run.decision == "deny"
    assert "/v1/workouts" in run.reason


@pytest.mark.parametrize(
    "command",
    [
        "curl https://api.hevyapp.com/v1/routines",
        "curl -X PUT -d @r.json https://api.hevyapp.com/v1/routines/r1",
        "wget https://api.hevyapp.com/v1/exercise_templates",
        "python3 - <<'EOF'\nimport urllib.request as u\n"
        "u.urlopen(u.Request('https://api.hevyapp.com/v1/routines/r1', method='PUT'))\nEOF",
    ],
)
def test_a_raw_call_on_another_hevy_path_asks_with_a_warning(command: str) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command))

    assert run.decision == "ask"
    assert "skips" in run.reason
    assert run.dry_runs == []


def test_a_raw_hevy_call_is_denied_where_no_prompt_exists() -> None:
    run = run_hook(
        "pre-tool-use", a_bash_call("curl https://api.hevyapp.com/v1/routines", mode="dontAsk")
    )

    assert run.decision == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "coach publish",
        "/home/a/.local/bin/coach publish",
        "python3 -m coach publish",
        "python3.12 -I -m coach publish",
        "uv run coach publish",
        "env COACH_X=1 coach publish",
        "git add -A && coach publish 2>&1 | tail -5",
        "bash -c 'coach publish'",
        "eval coach publish",
        'echo "$(coach publish)"',
        "echo `coach publish`",
        "(coach publish)",
        "sh -c \"bash -c 'coach publish'\"",
        "if true; then coach publish; fi",
        "for i in 1; do coach publish; done",
        "while true; do coach publish; done",
        "{ coach publish; }",
        "! coach publish",
        "f() { coach publish; }",
        "case x in x) coach publish;; esac",
        "nice coach publish",
        "nice -n 5 coach publish",
        "timeout 60 coach publish",
        "xargs coach publish",
        "nohup coach publish",
        "stdbuf -oL coach publish",
        "uvx coach publish",
        "uvx --from coach coach publish",
        "sudo -u me coach publish",
        "env -C /x coach publish",
        "uv run --with x coach publish",
        "timeout 5 python3 -m coach publish",
        "echo a#b; coach publish",
        "echo x # note\ncoach publish",
        "bash -o pipefail -c 'coach publish'",
        "bash -euo pipefail -c 'coach publish'",
        "bash --norc -c 'coach publish'",
        "bash --rcfile x -c 'coach publish'",
        "bash +O extglob -c 'coach publish'",
        "bash -c -e 'coach publish'",
    ],
)
def test_the_hook_finds_a_gated_verb_wherever_the_shell_runs_it(command: str) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command))

    assert run.decision == "ask"
    assert run.dry_runs[0][0] == ["publish", "--dry-run"]


def test_the_dry_run_runs_where_the_command_would() -> None:
    run = run_hook("pre-tool-use", a_bash_call("cd me && coach publish", cwd="/athletes"))

    assert run.dry_runs[0][1] == Path("/athletes/me")


def test_fields_are_dropped_from_the_dry_run_so_it_returns_its_hash() -> None:
    run = run_hook(
        "pre-tool-use", a_bash_call(f"coach plan apply x.toml --expect {HASH} --fields ok")
    )

    assert run.decision == "ask"
    assert run.dry_runs[0][0] == ["plan", "apply", "x.toml", "--expect", HASH, "--dry-run"]


@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("coach plan apply x.toml --expect $HASH", "only known when the shell runs"),
        ('coach plan apply x.toml --expect "$(cat hash)"', "only known when the shell runs"),
        ("coach plan apply 'x.toml --expect", "No closing quotation"),
        ("coach plan apply x.toml --bogus", "unknown option --bogus"),
    ],
)
def test_an_unreadable_command_asks_with_the_reason(command: str, why: str) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command))

    assert run.decision == "ask"
    assert why in run.reason
    assert run.dry_runs == []


@pytest.mark.parametrize(
    "command",
    [
        "H=api.hevyapp.com; curl https://$H/v1/workouts",
        "curl $(cat hevy-url)  # api.hevyapp.com",
        '"$(which coach)" publish',
        "echo 'coach publish' | bash",
        "bash -s < coach-publish.sh",
    ],
)
def test_a_program_or_hevy_url_known_only_when_the_shell_runs_asks(command: str) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command))

    assert run.decision == "ask"
    assert "cannot read" in run.reason
    assert run.dry_runs == []


def test_an_unreadable_command_is_denied_where_no_prompt_exists() -> None:
    run = run_hook("pre-tool-use", a_bash_call("coach publish 'oops", mode="dontAsk"))

    assert run.decision == "deny"


def test_a_deny_anywhere_in_the_command_denies_it_whole() -> None:
    run = run_hook(
        "pre-tool-use", a_bash_call("coach publish; curl https://api.hevyapp.com/v1/workouts")
    )

    assert run.decision == "deny"
    assert "/v1/workouts" in run.reason


def test_two_gated_verbs_ask_once_with_both_dry_runs() -> None:
    run = run_hook(
        "pre-tool-use", a_bash_call(f"coach plan apply x.toml --expect {HASH} && coach publish")
    )

    assert run.decision == "ask"
    assert "coach plan apply" in run.reason
    assert "coach publish" in run.reason


def test_a_tool_other_than_bash_gets_no_answer() -> None:
    stdin = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": "x"}, "permission_mode": "default"}
    )

    run = run_hook("pre-tool-use", stdin)

    assert run.stdout == ""


@pytest.mark.parametrize("stdin", ["not json", "[]", '{"tool_name": "Bash"}'])
def test_hook_input_it_cannot_read_is_denied(stdin: str) -> None:
    run = run_hook("pre-tool-use", stdin)

    assert run.code == 0
    assert run.decision == "deny"


def test_hook_input_without_a_command_asks_where_a_prompt_exists() -> None:
    stdin = json.dumps({"tool_name": "Bash", "tool_input": {}, "permission_mode": "default"})

    run = run_hook("pre-tool-use", stdin)

    assert run.decision == "ask"


def test_a_failure_inside_the_hook_asks_where_a_prompt_exists() -> None:
    def broken(argv: Any, cwd: Path) -> dict[str, Any]:
        return {"ok": True}

    run = run_hook(
        "pre-tool-use", a_bash_call(f"coach plan apply x.toml --expect {HASH}"), run_coach=broken
    )

    assert run.code == 0
    assert run.decision == "ask"


NEVER_ALLOWED = [
    *(f"coach plan apply x.toml{flag}" for flag in ("", f" --expect {HASH}", " --expect wp-old")),
    "coach publish",
    "curl https://api.hevyapp.com/v1/routines",
    "curl https://api.hevyapp.com/v1/workouts",
    "coach publish 'oops",
]


@pytest.mark.parametrize("command", NEVER_ALLOWED)
@pytest.mark.parametrize("mode", EVERY_MODE)
@pytest.mark.parametrize("dry_run", [clean_dry_run(), throwing], ids=["clean", "throwing"])
def test_no_path_answers_allow(command: str, mode: str | None, dry_run: Any) -> None:
    run = run_hook("pre-tool-use", a_bash_call(command, mode=mode), run_coach=dry_run)

    assert run.decision in ("ask", "deny")
