import hashlib
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.fake_hevy import FakeHevy
from support.hevy_payloads import a_workout, an_exercise
from support.planning_instance import CLOCK, ENGINE, a_planning_instance, adopt_the_squat_version
from support.planning_instance import coach as planning_coach
from support.plans import SQUAT_TEMPLATE

from coach.cli import app

SQUAT_TODAY = a_workout(
    "10000000-0000-4000-8000-00000000000a",
    updated_at="2026-10-30T08:05:00.000Z",
    start="2026-10-30T07:00:00+00:00",
    end="2026-10-30T08:00:00+00:00",
    exercises=[an_exercise(SQUAT_TEMPLATE, "Squat (Barbell)")],
)
UNMAPPED = a_workout(
    "10000000-0000-4000-8000-00000000000b",
    exercises=[an_exercise("C0FFEE01", "Hollow Hold")],
)
PULLING = {
    "checkin open": ("checkin", "open"),
    "plan draft": ("plan", "draft", "--week", "2026-11-02", "--out", "plan.toml"),
    "progress": ("progress",),
    "program adopt": ("program", "adopt", "v1.toml"),
}


def a_hevy_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, hevy: bool) -> Path:
    """The planning instance, with Hevy turned on after the adoption so no import has run."""
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = a_planning_instance(tmp_path / "athlete")
    monkeypatch.chdir(root)
    adopt_the_squat_version(root)
    if hevy:
        with (root / "coach.toml").open("a", encoding="utf-8") as config:
            config.write("\n[hevy]\n")
    return root


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_hevy_instance(tmp_path, monkeypatch, hevy=True)


def written(root: Path) -> tuple[str, ...]:
    """The store's bytes and every file under the instance, to show a run wrote nothing."""
    store = hashlib.sha256((root / ".coach" / "coach.db").read_bytes()).hexdigest()
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    return (store, *files)


def pulling(verb: str, hevy: FakeHevy | None = None) -> Run:
    return planning_coach(*PULLING[verb], hevy=hevy)


def test_checkin_open_shows_a_session_logged_in_hevy_with_no_import_run(instance: Path) -> None:
    run = pulling("checkin open", FakeHevy(CLOCK, workouts=[SQUAT_TODAY]))

    assert run.code == 0, run.stdout
    result = run.envelope["result"]
    assert result["pull"]["workouts"] == {"new": 1, "versioned": 0, "gone": 0, "back": 0}
    lifts = next(f for f in result["card"] if f["field"] == "lifts")
    assert [(r["exercise"], r["top_set"]["reps"]) for r in lifts["rows"]] == [("bb_back_squat", 5)]


@pytest.mark.parametrize("verb", PULLING)
def test_a_pulling_verb_pulls_first_and_carries_the_pull(instance: Path, verb: str) -> None:
    run = pulling(verb, FakeHevy(CLOCK, workouts=[UNMAPPED]))

    assert run.code == 0, run.stdout
    pull = run.envelope["result"]["pull"]
    assert (pull["kind"], pull["workouts"]["new"]) == ("full", 1)
    assert set(pull) == {"kind", "window", "workouts", "weigh_ins", "routines", "folders"}
    assert f"exercise_unmapped@workout:{UNMAPPED['id']}" in {
        w["key"] for w in run.envelope["warnings"]
    }


@pytest.mark.parametrize("verb", PULLING)
def test_hevy_unreachable_is_exit_4_and_writes_nothing(instance: Path, verb: str) -> None:
    hevy = FakeHevy(CLOCK, workouts=[SQUAT_TODAY])
    hevy.fail_next_get()
    before = written(instance)

    run = pulling(verb, hevy)

    assert (run.code, run.envelope["error"]["code"]) == (4, "hevy_unreachable")
    assert written(instance) == before


@pytest.mark.parametrize("verb", PULLING)
def test_hevy_on_with_no_key_is_exit_5(instance: Path, verb: str) -> None:
    run = run_coach(*PULLING[verb], clock=CLOCK)

    assert (run.code, run.envelope["error"]["code"]) == (5, "hevy_key_missing")


@pytest.mark.parametrize("verb", PULLING)
def test_with_no_hevy_table_a_pulling_verb_runs_with_no_pull(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    a_hevy_instance(tmp_path, monkeypatch, hevy=False)
    hevy = FakeHevy(CLOCK)

    run = pulling(verb, hevy)

    assert run.code == 0, run.stdout
    assert "pull" not in run.envelope["result"]
    assert hevy.calls == []
