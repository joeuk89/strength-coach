from contextlib import closing
from pathlib import Path

import pytest
from support.cli import Run, run_coach
from support.clock import FixedClock
from support.goals import WORKED
from support.history import a_logged_workout
from support.instances import an_instance

from coach.cli import app
from coach.store import exercises
from coach.store.catalogue import seed_catalogue
from coach.store.connection import open_store

ENGINE = "0.3.0"
NIGGLE = """
[[niggle]]
site = "left knee"
opened = 2026-10-20
date = 2026-10-20
status = "reported"
"""


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(app, "engine_version", lambda: ENGINE)
    root = an_instance(tmp_path, pin=ENGINE)
    monkeypatch.chdir(root)
    return root


def coach(*argv: str) -> Run:
    return run_coach(*argv, clock=FixedClock())


def test_checkin_open_returns_the_card_and_its_warnings(instance: Path) -> None:
    (instance / "n.toml").write_text(NIGGLE, encoding="utf-8")
    coach("record", "n.toml")

    run = coach("checkin", "open", "--date", "2026-10-30")

    assert run.code == 0
    result = run.envelope["result"]
    assert (result["tier"], result["window"]) == (
        "light",
        {"start": "2026-10-30", "end": "2026-10-30"},
    )
    assert [f["field"] for f in result["card"]] == [
        "header",
        "readiness",
        "sleep",
        "weight_phase",
        "niggles",
    ]
    assert result["card"][-1]["asks"] == [{"ask": "niggle_status", "about": "niggle:n-0001"}]
    assert [w["code"] for w in run.envelope["warnings"]] == ["niggle_unconstrained"]


def test_tier_deep_raises_the_tier(instance: Path) -> None:
    run = coach("checkin", "open", "--tier", "deep")

    assert run.envelope["result"]["tier"] == "deep"


def test_a_tier_other_than_light_or_deep_is_exit_1(instance: Path) -> None:
    run = coach("checkin", "open", "--tier", "heavy")

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")


def test_readiness_given_at_open_is_accepted(instance: Path) -> None:
    run = coach("checkin", "open", "--readiness", "poor")

    assert run.code == 0


def test_a_readiness_other_than_poor_ok_or_good_is_exit_1(instance: Path) -> None:
    run = coach("checkin", "open", "--readiness", "tired")

    assert (run.code, run.envelope["error"]["code"]) == (1, "invalid_argument")


def test_the_sleep_ask_carries_its_threshold_and_the_nights_it_wants(instance: Path) -> None:
    run = coach("checkin", "open", "--date", "2026-10-30")

    sleep = next(f for f in run.envelope["result"]["card"] if f["field"] == "sleep")
    assert sleep["asks"] == [
        {
            "ask": "sleep_nights",
            "record": "sleep_night",
            "under_hours": 7,
            "nights": [f"2026-10-{d}" for d in range(23, 30)],
            "give": "night and hours for every night under 7 hours; other nights optional",
        }
    ]


def test_the_phase_line_names_its_rate_units(instance: Path) -> None:
    (instance / ".coach").mkdir()
    with closing(open_store(instance / ".coach" / "coach.db")) as conn, conn:
        seed_catalogue(conn)
    (instance / "goal.toml").write_text(WORKED, encoding="utf-8")
    assert coach("goal", "adopt", "goal.toml").code == 0

    run = coach("checkin", "open", "--date", "2026-10-30")

    weight = next(f for f in run.envelope["result"]["card"] if f["field"] == "weight_phase")
    assert weight["phase"] == {
        "id": "ph-0001",
        "kind": "maintenance",
        "target_rate": 0.0,
        "observed_rate": None,
        "rate_units": "pct_bw_per_week",
        "until": {"kind": "coachs_call", "value": None},
    }


def test_a_lift_doubt_carries_its_reason_and_the_sets_it_quotes(instance: Path) -> None:
    (instance / ".coach").mkdir()
    with closing(open_store(instance / ".coach" / "coach.db")) as conn:
        with conn:
            seed_catalogue(conn)
            exercises.update(conn, "bb_back_squat", {"hevy_template_id": "SQ-0001"})
        a_logged_workout(conn, "w-1", "2026-10-30", ("SQ-0001", ((80, 5, 8.0),)))
        a_logged_workout(conn, "w-2", "2026-10-30", ("SQ-0001", ((50, 5, 6.0),)))

    run = coach("checkin", "open", "--date", "2026-10-30")

    lifts = next(f for f in run.envelope["result"]["card"] if f["field"] == "lifts")
    doubt, soreness = lifts["asks"]
    assert soreness == {"ask": "soreness_and_niggles"}
    assert (doubt["ask"], doubt["about"], doubt["reason"]) == (
        "lift_doubt",
        "exercise:bb_back_squat",
        "exposures_disagree",
    )
    assert [(e["logged"], e["e1rm"]) for e in doubt["params"]["exposures"]] == [
        ([{"load": 80.0, "reps": 5, "rpe": 8.0}], 98.67),
        ([{"load": 50.0, "reps": 5, "rpe": 6.0}], 65.0),
    ]


def test_the_schema_lists_the_phase_rate_units(instance: Path) -> None:
    output = coach("schema", "checkin open").envelope["result"]["output"]

    phase = output["properties"]["card"]["items"]["properties"]["phase"]
    assert phase["properties"]["rate_units"] == {"const": "pct_bw_per_week"}


def test_a_card_field_with_fifteen_rows_returns_all_fifteen(instance: Path) -> None:
    activity = '[[activity]]\ndate = 2026-10-30\nkind = "walk"\nminutes = {}\nrpe = 3\n'
    draft = "\n".join(activity.format(10 + n) + "quality = false\n" for n in range(15))
    (instance / "a.toml").write_text(draft, encoding="utf-8")
    assert coach("record", "a.toml").code == 0

    card = coach("checkin", "open", "--date", "2026-10-30").envelope["result"]["card"]

    [field] = [f for f in card if f["field"] == "activities"]
    assert (len(field["rows"]), field["count"], field["truncated"]) == (15, 15, False)
