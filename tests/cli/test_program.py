import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.instances import an_instance
from support.kit_fixtures import INVENTORY, TABLES
from support.program_drafts import CUSTOM_EXERCISES, WORKED_DRAFT_COMPLETE, a_draft, toml
from support.programs import GYM, HOME

from coach.cli import app
from coach.core.goal import Goal
from coach.store import exercises, goals
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

ENGINE = "0.3.0"
CLOCK = FixedClock()


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An instance at the fixture kit in pounds, its store seeded with the catalogue, the
    custom exercises and a hypertrophy Goal on bench and the pull-up."""
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
        for n, (id_, columns) in enumerate(CUSTOM_EXERCISES.items(), start=1):
            exercises.insert(
                conn,
                {
                    "id": id_,
                    "name": id_,
                    "pattern": "core",
                    "muscles": {"primary": [], "secondary": []},
                    "hevy_template_id": f"C-{n}",
                    "source": "record",
                    **columns,
                },
            )
        goals.insert(
            conn,
            id_="g-0001",
            goal=Goal("hypertrophy", "first goal", ("bb_bench_press", "pull_up"), ""),
            milestone_ids=(),
            adopted="2026-10-01",
            draft_hash="sha256:g",
            recorded_at="2026-10-01T12:00:00+00:00",
        )
    conn.close()
    monkeypatch.chdir(root)
    return root


def coach(*argv: str) -> Any:
    return run_coach(*argv, clock=CLOCK)


def a_draft_file(root: Path, text: str | bytes, name: str = "v1.toml") -> str:
    path = root / ".coach" / name
    path.write_bytes(text.encode() if isinstance(text, str) else text)
    return f".coach/{name}"


def test_program_adopt_records_the_worked_draft(instance: Path) -> None:
    run = coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    assert run.code == 0, run.stdout
    assert run.envelope["result"] == {
        "version": "pv-1",
        "kind": "redesign",
        "position": "A",
        "block": {"id": "b-2026-10-30", "reset": True},
        "acknowledgements": [
            {
                "flag": "scheme_off_emphasis@line:a-sat-pull/pull_up",
                "because": "coach_judgement",
                "text": "The pull-up progresses through the assistance ladder and negatives; "
                "the weekly single is the measure.",
            }
        ],
        "no_op": False,
    }


def test_program_adopt_dry_run_shows_the_diff_and_start_loads_and_writes_nothing(
    instance: Path,
) -> None:
    run = coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE), "--dry-run")

    result = run.envelope["result"]
    assert run.code == 0
    assert result["diff"]["version"]["dose"]["filled"] is True
    assert result["start_loads"][0] == {
        "session": "a-mon-lower",
        "exercise": "bb_back_squat",
        "start_load": 120,
        "units": "lb",
        "kg": 54.4311,
    }
    assert result["violations"] == [] and result["warnings"] == []
    conn = sqlite3.connect(instance / ".coach" / "coach.db")
    assert conn.execute("SELECT count(*) FROM program_version").fetchone() == (0,)


def test_a_draft_with_a_violation_is_exit_1_with_its_code_and_every_flag(instance: Path) -> None:
    draft = a_draft(location="cabin")

    run = coach("program", "adopt", a_draft_file(instance, toml(draft)))

    assert run.code == 1
    error = run.envelope["error"]
    assert error["code"] == "location_unknown"
    assert [flag["key"] for flag in error["violations"]] == ["location_unknown@version:pv-1"]


def test_a_stale_kit_at_the_draft_location_is_exit_5_kit_tables_stale(instance: Path) -> None:
    inventory = instance / "kit" / "home.json"
    inventory.write_text(inventory.read_text() + "\n")

    run = coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    assert run.code == 5
    assert run.envelope["error"]["code"] == "kit_tables_stale"


def test_redesign_with_position_and_amend_keeping_it(instance: Path) -> None:
    draft = a_draft()
    draft["schedule"] = {"rotation": ["A", "B"], "A": {"mon": "push"}, "B": {"wed": "push"}}
    coach("program", "adopt", a_draft_file(instance, toml(draft)), "--position", "B")

    amend = coach(
        "program", "adopt", a_draft_file(instance, toml({**draft, "kind": "amend"}), "v2.toml")
    )

    assert amend.envelope["result"]["position"] == "B"
    assert amend.envelope["result"]["block"] == {"id": "b-2026-10-30", "reset": False}


def test_program_show_reads_the_version_in_force(instance: Path) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    run = coach("program", "show")

    result = run.envelope["result"]
    assert (result["version"], result["kind"], result["emphasis"], result["adopted"]) == (
        "pv-1",
        "redesign",
        "hypertrophy",
        "2026-10-30",
    )
    assert result["sessions"][:2] == [
        {"id": "pt-tuesday", "lines": 0},
        {"id": "a-mon-lower", "lines": 6},
    ]
    assert (result["count"], result["truncated"]) == (11, True)


def test_program_show_draft_writes_a_draft_that_re_adopts_as_an_amend_with_an_empty_diff(
    instance: Path,
) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    shown = coach("program", "show", "--draft")
    path = shown.envelope["result"]["path"]
    dry = coach("program", "adopt", path, "--dry-run")
    adopted = coach("program", "adopt", path)

    assert path == ".coach/drafts/2026-10-30-program.toml"
    assert shown.envelope["result"]["hash"].startswith("sha256:")
    assert dry.envelope["result"]["diff"]["empty"] is True
    assert adopted.envelope["result"]["kind"] == "amend"
    assert adopted.envelope["result"]["version"] == "pv-2"


def test_program_show_draft_again_keeps_the_path_and_an_edited_draft_moves_to_a_suffix(
    instance: Path,
) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))
    first = coach("program", "show", "--draft").envelope["result"]["path"]
    same = coach("program", "show", "--draft").envelope["result"]["path"]
    (instance / first).write_text((instance / first).read_text() + "\n# edited\n")

    moved = coach("program", "show", "--draft").envelope["result"]["path"]

    assert first == same == ".coach/drafts/2026-10-30-program.toml"
    assert moved == ".coach/drafts/2026-10-30-program-2.toml"


def test_program_show_draft_to_an_out_path_with_other_content_is_draft_exists(
    instance: Path,
) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))
    (instance / "mine.toml").write_text("name = 'mine'\n")

    run = coach("program", "show", "--draft", "--out", "mine.toml")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "draft_exists"


def test_status_reports_the_program_version_in_force(instance: Path) -> None:
    assert coach("status").envelope["result"]["program"] is None
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    run = coach("status")

    assert run.envelope["result"]["program"] == {
        "version": "pv-1",
        "kind": "redesign",
        "emphasis": "hypertrophy",
        "adopted": "2026-10-30",
    }
