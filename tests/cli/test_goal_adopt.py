from contextlib import closing
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.goals import STRENGTH, WORKED, opening, with_phase
from support.instances import an_instance

from coach.cli import app
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

ENGINE = "0.3.0"


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE)
    (root / ".coach").mkdir()
    with closing(open_store(root / ".coach" / "coach.db")) as conn, conn:
        seed_catalogue(conn)
    monkeypatch.chdir(root)
    return root


def adopt(root: Path, text: str, name: str = "goal.toml") -> Run:
    (root / name).write_text(text, encoding="utf-8")
    return run_coach("goal", "adopt", name, clock=FixedClock())


def test_the_worked_draft_adopts_and_status_shows_the_goal_and_the_phase(instance: Path) -> None:
    run = adopt(instance, WORKED)

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["goal_id"] == "g-0001"
    assert result["kind"] == "hypertrophy"
    assert result["priority_lifts"] == ["bb_bench_press", "pull_up"]
    assert result["milestones"] == ["m-0001", "m-0002", "m-0003"]
    assert result["phase"] == {"opened": "ph-0001", "closed": None}
    assert result["superseded"] is None
    assert result["diff"] is None
    status = run_coach("status").envelope["result"]
    assert status["goal"] == {
        "id": "g-0001",
        "kind": "hypertrophy",
        "priority_lifts": ["bb_bench_press", "pull_up"],
    }
    assert status["phase"] == {
        "id": "ph-0001",
        "kind": "maintenance",
        "until": {"kind": "coachs_call", "value": None},
    }


def test_a_second_goal_supersedes_the_first_and_the_envelope_carries_the_diff(
    instance: Path,
) -> None:
    adopt(instance, WORKED)

    run = adopt(instance, STRENGTH, "second.toml")

    result = run.envelope["result"]
    assert (result["goal_id"], result["superseded"]) == ("g-0002", "g-0001")
    assert result["diff"]["kind"] == {"from": "hypertrophy", "to": "strength"}
    assert result["diff"]["why"] is True
    assert run_coach("status").envelope["result"]["goal"]["id"] == "g-0002"


def test_the_same_draft_again_returns_the_same_goal_id(instance: Path) -> None:
    first = adopt(instance, WORKED)

    second = adopt(instance, WORKED)

    assert second.code == 0
    assert second.envelope["result"] == first.envelope["result"]


def test_a_dated_until_shows_its_date_in_status(instance: Path) -> None:
    adopt(
        instance,
        with_phase(
            STRENGTH,
            'open = { kind = "surplus", until = { kind = "date", value = 2027-03-01 }, '
            'because = "bulk" }',
        ),
    )

    phase = run_coach("status").envelope["result"]["phase"]

    assert phase["until"] == {"kind": "date", "value": "2027-03-01"}


def test_closing_and_opening_in_one_file_succeeds(instance: Path) -> None:
    adopt(instance, WORKED)

    run = adopt(
        instance,
        with_phase(STRENGTH, 'close = { because = "recomp done" }\n' + opening("surplus")),
        "second.toml",
    )

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["phase"] == {"opened": "ph-0002", "closed": "ph-0001"}


@pytest.mark.parametrize(
    ("draft", "code"),
    [
        (STRENGTH.replace('["bb_bench_press"]', '["bench"]'), "unknown_exercise"),
        (
            STRENGTH.replace('["bb_bench_press"]', '["bb_bench_press", "bb_bench_press"]'),
            "priority_lift_duplicate",
        ),
        (STRENGTH + '\n[[milestones]]\nexercise = "bb_deadlift"\n', "milestone_target_missing"),
        (with_phase(STRENGTH, opening("surplus")), "phase_already_open"),
    ],
)
def test_each_refusal_is_exit_1_with_its_code(instance: Path, draft: str, code: str) -> None:
    adopt(instance, WORKED)

    run = adopt(instance, draft, "refused.toml")

    assert run.code == 1
    assert run.envelope["ok"] is False
    assert run.envelope["error"]["code"] == code
    assert run_coach("status").envelope["result"]["goal"]["id"] == "g-0001"
