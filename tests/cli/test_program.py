import shutil
import sqlite3
import tomllib
from pathlib import Path
from typing import Any

import pytest
from support.cli import run_coach
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.fixture_instances import serving
from support.instances import an_instance
from support.kit_fixtures import INVENTORY, TABLES
from support.plans import a_plan_override, an_approved_plan
from support.program_drafts import (
    BALANCE_BOARD_DRAFT,
    CUSTOM_EXERCISES,
    WORKED_DRAFT_COMPLETE,
    a_draft,
    a_line,
    a_session,
    toml,
)
from support.programs import GYM, HOME

from coach.cli import app
from coach.core.config import WEEKDAYS
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
    every_day = ", ".join(f'"{day}"' for day in WEEKDAYS)
    text = text.replace('"monday", "wednesday", "friday"', every_day, 1)
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
    return run_coach(*argv, clock=CLOCK, make_client=serving(FakeHevy(CLOCK)))


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


def test_program_adopt_puts_its_warnings_in_the_envelope_with_their_rn(instance: Path) -> None:
    run = coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    [warning] = run.envelope["warnings"]
    assert warning["key"] == "scheme_off_emphasis@line:a-sat-pull/pull_up"
    assert warning["severity"] == "warning" and warning["rn"] == "rn:goal-programming §4"
    assert warning["params"]["scheme"] == "hold"
    assert warning["left"]["because"] == "coach_judgement"


def test_a_stale_acknowledgement_is_exit_1_acknowledgement_unmatched(instance: Path) -> None:
    stale = WORKED_DRAFT_COMPLETE.replace("a-sat-pull/pull_up", "a-sat-pull/assisted_pull_up")

    run = coach("program", "adopt", a_draft_file(instance, stale))

    assert run.code == 1
    assert run.envelope["error"]["code"] == "acknowledgement_unmatched"


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
    assert [(w["key"], w["left"]["source"]) for w in run.envelope["warnings"]] == [
        ("scheme_off_emphasis@line:a-sat-pull/pull_up", "version")
    ]
    conn = sqlite3.connect(instance / ".coach" / "coach.db")
    assert conn.execute("SELECT count(*) FROM program_version").fetchone() == (0,)


def test_program_adopt_dry_run_lists_each_session_with_its_minutes_and_estimate(
    instance: Path,
) -> None:
    run = coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE), "--dry-run")

    sessions = run.envelope["result"]["sessions"]
    assert sessions[:3] == [
        {"id": "pt-tuesday", "minutes": None, "estimate": None},
        {"id": "a-mon-lower", "minutes": 60, "estimate": 49},
        {"id": "b-sat-push", "minutes": 90, "estimate": 22},
    ]
    assert len(sessions) == 11


def test_the_real_program_adopt_output_has_no_sessions(instance: Path) -> None:
    run = coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    assert run.code == 0
    assert "sessions" not in run.envelope["result"]


def test_a_draft_with_a_violation_is_exit_1_with_its_code_and_every_flag(instance: Path) -> None:
    draft = a_draft(location="cabin")

    run = coach("program", "adopt", a_draft_file(instance, toml(draft)))

    assert run.code == 1
    error = run.envelope["error"]
    assert error["code"] == "location_unknown"
    assert [flag["key"] for flag in error["violations"]] == ["location_unknown@version:pv-1"]


def test_with_hevy_on_a_template_value_hevy_rejects_is_exit_1_and_nothing_adopts(
    instance: Path,
) -> None:
    with (instance / "coach.toml").open("a", encoding="utf-8") as config:
        config.write("\n[hevy]\n")
    ring_row = {
        "name": "Ring row",
        "load_mode": "bodyweight",
        "equipment_kind": "bodyweight",
        "pattern": "horizontal_pull",
        "muscles": {"primary": ["lats"], "secondary": []},
        "hevy_title": "Ring Row",
        "hevy_exercise_type": "reps_only",
        "hevy_equipment": "bands",
        "hevy_muscle_group": "lats",
    }
    line = a_line(
        "custom_ring_row", sets=[{"count": 3, "reps": [10, 15], "rpe": 8}], start_load=None
    )
    draft = a_draft(a_session("push", a_line(), line), exercise={"custom_ring_row": ring_row})

    run = run_coach(
        "program",
        "adopt",
        a_draft_file(instance, toml(draft)),
        env={"HEVY_API_KEY": "a-key"},
        clock=CLOCK,
        make_client=serving(FakeHevy(CLOCK)),
    )

    assert run.code == 1, run.stdout
    error = run.envelope["error"]
    assert error["code"] == "hevy_template_value_unknown"
    [flag] = error["violations"]
    assert flag["params"] == {
        "exercise_id": "custom_ring_row",
        "column": "hevy_equipment",
        "value": "bands",
    }
    assert coach("program", "show").code != 0


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


def a_week_with_a_swap_and_a_pin(root: Path) -> None:
    conn = open_store(root / ".coach" / "coach.db")
    plan_id = an_approved_plan(conn, "2026-10-26")
    a_plan_override(
        conn,
        plan_id,
        "swap_exercise",
        "a-mon-lower",
        "bb_back_squat",
        to="goblet_squat",
        start_load=25,
    )
    a_plan_override(conn, plan_id, "pin_load", "b-sat-push", "bb_bench_press", load=100)
    conn.close()


def test_apply_plan_folds_a_swap_and_a_pin_into_a_draft_that_adopts_as_an_amend(
    instance: Path,
) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))
    a_week_with_a_swap_and_a_pin(instance)

    shown = coach("program", "show", "--draft", "--apply-plan", "2026-10-26")
    text = (instance / shown.envelope["result"]["path"]).read_text()
    adopted = coach("program", "adopt", shown.envelope["result"]["path"])

    assert shown.envelope["result"]["folded"] == [
        {"session": "a-mon-lower", "exercise": "bb_back_squat", "kind": "swap_exercise"},
        {"session": "b-sat-push", "exercise": "bb_bench_press", "kind": "pin_load"},
    ]
    sessions = {s["id"]: s for s in tomllib.loads(text)["session"]}
    assert sessions["a-mon-lower"]["line"][0]["exercise"] == "goblet_squat"
    assert sessions["a-mon-lower"]["line"][0]["start_load"] == 25
    assert "start_load = 100  # folded pin" in text
    assert adopted.code == 0, adopted.stdout
    assert adopted.envelope["result"]["kind"] == "amend"


def test_apply_plan_on_a_week_with_no_approved_plan_is_refused(instance: Path) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    run = coach("program", "show", "--draft", "--apply-plan", "2026-10-26")

    assert run.code == 1
    assert "2026-10-26" in run.envelope["error"]["message"]
    assert run.envelope["error"]["code"] == "state_conflict"


def test_apply_plan_needs_draft(instance: Path) -> None:
    run = coach("program", "show", "--apply-plan", "2026-10-26")

    assert run.envelope["error"]["code"] == "invalid_argument"


def test_program_show_prints_every_rung_of_the_balance_board_ladder(instance: Path) -> None:
    adopted = coach("program", "adopt", a_draft_file(instance, BALANCE_BOARD_DRAFT))

    run = coach("program", "show")

    assert adopted.code == 0, adopted.stdout
    [ladder] = run.envelope["result"]["ladders"]
    assert (ladder["session"], ladder["exercise"]) == (
        "daily-balance",
        "custom_balance_board_stand",
    )
    assert ladder["rungs"][0] == {
        "rung": 1,
        "exercise": "custom_balance_board_stand",
        "cues": "both feet, still, near a wall · soft knees · eyes on a point ahead",
        "sets": [{"count": 2, "duration_s": 30, "rpe": 5}],
        "criterion": {"duration_s": 30, "rpe_at_most": 5, "exposures": 2},
        "standing": True,
    }
    assert [(r["rung"], r["exercise"], r["standing"]) for r in ladder["rungs"]] == [
        (1, "custom_balance_board_stand", True),
        (2, "custom_balance_board_tilt", False),
        (3, "custom_balance_board_eyes_closed", False),
        (4, "custom_balance_board_one_foot", False),
        (5, "custom_balance_board_one_foot_eyes_closed", False),
    ]
    assert ladder["rungs"][2]["criterion"] == {"duration_s": 45, "rpe_at_most": 6, "exposures": 3}


def test_program_show_of_a_version_with_no_ladder_prints_no_ladders(instance: Path) -> None:
    coach("program", "adopt", a_draft_file(instance, WORKED_DRAFT_COMPLETE))

    assert coach("program", "show").envelope["result"]["ladders"] == []


def test_program_show_marks_the_rung_a_ladder_rung_decision_names(instance: Path) -> None:
    coach("program", "adopt", a_draft_file(instance, BALANCE_BOARD_DRAFT))
    decision = (
        '[[decision]]\nkind = "ladder_rung"\nsession = "daily-balance"\n'
        'exercise = "custom_balance_board_stand"\nrung = 3\nbecause = "progress"\n'
        'text = "Steady tilts; the athlete said yes."\n'
    )
    recorded = coach("record", a_draft_file(instance, decision, "rung.toml"))

    [ladder] = coach("program", "show").envelope["result"]["ladders"]

    assert recorded.code == 0, recorded.stdout
    assert [r["rung"] for r in ladder["rungs"] if r["standing"]] == [3]
