import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from support.cli import run_coach

from coach.cli import registry
from coach.cli.registry import declarations
from coach.render.instance_files import settings_json

ROOT = Path(__file__).resolve().parents[2]
INSTALL_HINT = "coach engine not installed: uv tool install"


def hook_commands() -> dict[str, str]:
    document = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return {
        event: hook["command"]
        for event, matchers in document["hooks"].items()
        for matcher in matchers
        for hook in matcher["hooks"]
    }


def test_the_plugin_declares_session_start_and_pre_tool_use_on_bash_only() -> None:
    document = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    assert set(document["hooks"]) == {"SessionStart", "PreToolUse"}
    assert [m.get("matcher") for m in document["hooks"]["PreToolUse"]] == ["Bash"]
    assert set(hook_commands()) == {"SessionStart", "PreToolUse"}


@pytest.mark.parametrize(
    ("event", "argument"), [("SessionStart", "session-start"), ("PreToolUse", "pre-tool-use")]
)
def test_each_hook_calls_coach_hook_with_its_event(event: str, argument: str) -> None:
    assert f"coach-hook {argument}" in hook_commands()[event]


@pytest.mark.parametrize("event", ["SessionStart", "PreToolUse"])
def test_with_the_engine_absent_the_guard_prints_the_install_hint_and_exits_0(
    event: str, tmp_path: Path
) -> None:
    completed = subprocess.run(
        ["/bin/sh", "-c", hook_commands()[event]],
        env={"PATH": ""},
        cwd=tmp_path,
        input="{}",
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.startswith(INSTALL_HINT)


def test_the_repo_is_its_own_marketplace_listing_the_one_plugin_at_the_root() -> None:
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )

    assert [(p["name"], p["source"]) for p in marketplace["plugins"]] == [(plugin["name"], "./")]


def test_coach_hook_is_a_second_console_script() -> None:
    pyproject: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))

    assert pyproject["project"]["scripts"]["coach-hook"] == "coach.cli.hook.app:run"


def test_coach_hook_is_not_a_leaf_and_leaves_the_count_unchanged() -> None:
    before = len(declarations())
    registry.declarations.cache_clear()

    import coach.cli.hook.app  # noqa: F401  # pyright: ignore[reportUnusedImport]

    assert len(registry.declarations()) == before
    assert not any("hook" in d.name for d in registry.declarations())


def test_coach_hook_is_absent_from_help_schema_and_the_permission_rules() -> None:
    asked = [d.name for d in declarations() if d.writes in ("hevy", "git")]

    for text in (run_coach("--help").stdout, run_coach("schema").stdout, settings_json(asked)):
        assert "coach-hook" not in text
