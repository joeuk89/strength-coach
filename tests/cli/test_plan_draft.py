import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.instances import an_instance
from support.kit_fixtures import INVENTORY, TABLES
from support.plans import SQUAT_LINE, a_note
from support.program_drafts import a_draft, a_session, toml
from support.programs import GYM, HOME

from coach.cli import app
from coach.cli.registry import declarations
from coach.core.goal import Goal
from coach.store import goals
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

ENGINE = "0.3.0"
CLOCK = FixedClock()


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An instance at the fixture kit in pounds with a one-session squat version adopted."""
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path / "athlete", pin=ENGINE, location={"home": HOME, "gym": GYM})
    text = (root / "coach.toml").read_text().replace('units = "kg"', 'units = "lb"', 1)
    (root / "coach.toml").write_text(text)
    (root / "kit").mkdir()
    shutil.copyfile(INVENTORY, root / "kit" / "home.json")
    shutil.copyfile(TABLES, root / "kit" / "home.achievable.json")
    (root / ".coach").mkdir()
    conn = open_store(root / ".coach" / "coach.db")
    with conn:
        seed_catalogue(conn)
        goals.insert(
            conn,
            id_="g-0001",
            goal=Goal("hypertrophy", "first goal", ("bb_back_squat",), ""),
            milestone_ids=(),
            adopted="2026-10-01",
            draft_hash="sha256:g",
            recorded_at="2026-10-01T12:00:00+00:00",
        )
    a_note(
        conn,
        "an-0001",
        "2026-10-28",
        "Knee felt tight on the stairs.",
        about="exercise:bb_back_squat",
        at="2026-10-28T09:00:00+00:00",
    )
    conn.close()
    monkeypatch.chdir(root)
    (root / "v1.toml").write_bytes(toml(a_draft(a_session("lower", SQUAT_LINE))))
    assert coach("program", "adopt", "v1.toml").code == 0
    return root


def coach(*argv: str) -> Any:
    return run_coach(*argv, clock=CLOCK)


def test_plan_draft_writes_the_draft_and_returns_its_summary(instance: Path) -> None:
    run = coach("plan", "draft", "--week", "2026-11-02")

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["path"] == ".coach/drafts/2026-10-30-plan.toml"
    assert result["hash"].startswith("sha256:")
    assert result["week"] == "2026-11-02"
    assert result["supersedes"] is None
    assert result["lines"] == 1
    assert result["position"] == {"week": "A", "source": "program_adopt"}
    assert [f["code"] for f in result["flags"]] == ["rotation_unconfirmed"]
    assert result["notes"] == [
        {
            "date": "2026-10-28",
            "text": "Knee felt tight on the stairs.",
            "about": "exercise:bb_back_squat",
        }
    ]
    text = (instance / result["path"]).read_text()
    assert 'text = "Knee felt tight on the stairs."' in text
    assert 'change = "first prescription"' in text


def test_each_flag_key_in_the_summary_carries_the_params_hash_its_draft_table_carries(
    instance: Path,
) -> None:
    result = coach("plan", "draft", "--week", "2026-11-02").envelope["result"]

    [row] = result["flags"]
    [table] = tomllib.loads((instance / result["path"]).read_text())["flag"]
    assert row == {
        "code": "rotation_unconfirmed",
        "severity": "violation",
        "count": 1,
        "keys": [
            {
                "key": "rotation_unconfirmed@week:2026-11-02",
                "params_hash": (
                    "sha256:15a498510e347e58c8eeb3465628f15434d46e9ce0be0adeb0f5fc56f30ddc46"
                ),
            }
        ],
    }
    assert table["params_hash"] == row["keys"][0]["params_hash"]


def test_the_declared_flag_keys_require_the_key_and_params_hash() -> None:
    declared = next(d for d in declarations() if d.name == "plan draft")
    properties: Any = declared.output["properties"]
    row = properties["flags"]["items"]

    assert set(row["required"]) == {"code", "severity", "count", "keys"}
    assert {"key", "params_hash"} <= set(row["properties"]["keys"]["items"]["required"])


def test_plan_draft_twice_on_an_unchanged_store_returns_the_same_path_and_hash(
    instance: Path,
) -> None:
    first = coach("plan", "draft").envelope["result"]
    second = coach("plan", "draft").envelope["result"]

    assert (second["path"], second["hash"]) == (first["path"], first["hash"])


def test_after_an_edit_to_the_draft_plan_draft_writes_the_next_suffix(instance: Path) -> None:
    first = coach("plan", "draft").envelope["result"]
    path = instance / first["path"]
    path.write_text(path.read_text().replace("confirmed = false", "confirmed = true"))

    second = coach("plan", "draft").envelope["result"]

    assert second["path"] == ".coach/drafts/2026-10-30-plan-2.toml"
    assert second["hash"] == first["hash"]


def test_out_naming_a_file_with_other_content_is_exit_1_draft_exists(instance: Path) -> None:
    (instance / "mine.toml").write_text("week = 2026-11-02\n")

    run = coach("plan", "draft", "--out", "mine.toml")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "draft_exists"


def test_a_week_that_is_not_a_date_is_exit_1(instance: Path) -> None:
    run = coach("plan", "draft", "--week", "next")

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")


def test_stale_kit_tables_are_exit_5_kit_tables_stale(instance: Path) -> None:
    (instance / "kit" / "home.json").write_text("{}")

    run = coach("plan", "draft")

    assert (run.code, run.envelope["error"]["code"]) == (5, "kit_tables_stale")


def test_status_shows_no_plan_in_force_and_the_rotation_position(instance: Path) -> None:
    result = coach("status").envelope["result"]

    assert result["plan"] is None
    assert result["rotation"] == {"week": "2026-10-26", "position": "A", "source": "program_adopt"}
