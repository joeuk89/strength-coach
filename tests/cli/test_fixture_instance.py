import json
from pathlib import Path

from support.fake_hevy import FakeHevy
from support.fixture_instance import tree
from support.fixture_instances import CLOCK, coach, hevy_holding, instance, rebuilt
from support.hevy_payloads import a_set, a_workout, an_exercise, an_updated_event

__all__ = ["instance", "rebuilt"]

PLAN = ".coach/drafts/next.toml"
BENCH = an_exercise("FX-BB_BENCH_PRESS", "Bench Press (Barbell)", a_set(weight_kg=110.0, reps=8))
TODAYS = a_workout(
    "10000000-0000-4000-8000-000000000001",
    updated_at="2026-10-30T08:05:00.000Z",
    start="2026-10-30T07:00:00+00:00",
    end="2026-10-30T08:00:00+00:00",
    exercises=[BENCH],
)


def next_weeks_plan(root: Path) -> str:
    drafted = coach("plan", "draft", "--week", "2026-11-02", "--out", PLAN).envelope["result"]
    draft = root / str(drafted["path"])
    draft.write_text(draft.read_text().replace("confirmed = false", "confirmed = true"))
    return PLAN


def test_the_default_card_keeps_every_lift_and_activity_row(instance: Path) -> None:
    card = {f["field"]: f for f in coach("checkin", "open").envelope["result"]["card"]}

    lifts, activities = card["lifts"], card["activities"]
    assert (len(lifts["rows"]), lifts["count"], lifts["truncated"]) == (4, 4, False)
    assert (len(activities["rows"]), activities["count"], activities["truncated"]) == (1, 1, False)


def test_exit_0_status_reads_the_fixture_instance(instance: Path) -> None:
    run = coach("status")

    assert run.code == 0
    result = run.envelope["result"]
    assert result["plan"]["week"] == "2026-10-26"
    assert result["plan"]["routines"] == {"verified": 11, "unverified": []}
    assert result["workouts"] == {"hevy": 357, "manual": 11}


def test_status_keys_follow_the_order_where_we_stand_is_read_in(instance: Path) -> None:
    result = coach("status").envelope["result"]

    assert list(result) == [
        "engine",
        "hevy",
        "workouts",
        "store_schema_version",
        "kit",
        "plan",
        "rotation",
        "program",
        "goal",
        "phase",
        "block",
        "check_in",
        "niggles",
        "follow_ups_due",
        "decisions",
        "observations",
        "export",
    ]


def test_exit_1_an_unknown_view(instance: Path) -> None:
    run = coach("query", "colours")

    assert run.code == 1
    assert run.envelope["error"]["code"] == "invalid_argument"


def test_exit_3_a_routine_moved_in_hevy_since_the_import(instance: Path) -> None:
    plan = next_weeks_plan(instance)
    digest = coach("plan", "apply", plan, "--dry-run").envelope["result"]["write_plan_hash"]
    hevy = hevy_holding(instance, CLOCK)
    hevy.move_routine("fake-routine-0001", "2026-10-29T08:00:00+00:00")

    run = coach("plan", "apply", plan, "--expect", digest, hevy=hevy)

    assert run.code == 3
    assert run.envelope["error"]["code"] == "routine_moved"
    assert hevy.calls == [("GET", "/v1/routines/fake-routine-0001")]


def a_mirror_without_the_folder(root: Path, title: str) -> None:
    """Rebuild the store from an export that holds no folder titled `title`."""
    folders = root / "export" / "folder.jsonl"
    rows = folders.read_text().splitlines(keepends=True)
    kept = [row for row in rows if json.loads(row)["title"] != title]
    folders.write_text("".join(kept))
    manifest_path = root / "export" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tables"]["folder"] = len(kept)
    manifest_path.write_text(json.dumps(manifest))
    (root / ".coach" / "coach.db").unlink()


def test_exit_3_two_hevy_folders_share_an_engine_title(instance: Path) -> None:
    a_mirror_without_the_folder(instance, "Program")
    plan = next_weeks_plan(instance)
    digest = coach("plan", "apply", plan, "--dry-run").envelope["result"]["write_plan_hash"]
    hevy = hevy_holding(instance, CLOCK, more_folders=("Program", "Program"))

    run = coach("plan", "apply", plan, "--expect", digest, hevy=hevy)

    assert run.code == 3
    assert run.envelope["error"]["code"] == "folder_title_shared"
    assert [call for call in hevy.calls if call[0] != "GET"] == []


def test_a_pull_past_a_shared_engine_folder_title_still_opens_the_check_in(
    instance: Path,
) -> None:
    hevy = hevy_holding(instance, CLOCK, more_folders=("Program",))

    run = coach("checkin", "open", hevy=hevy)

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["pull"]["folders"] == 0


def test_exit_4_hevy_unreachable_on_import(instance: Path) -> None:
    hevy = hevy_holding(instance, CLOCK)
    hevy.fail_next_get()

    run = coach("import", hevy=hevy)

    assert run.code == 4
    assert run.envelope["error"]["code"] == "hevy_unreachable"


def test_exit_5_hevy_on_with_no_key(instance: Path) -> None:
    run = coach("import", env={})

    assert run.code == 5
    assert run.envelope["error"]["code"] == "hevy_key_missing"


def test_import_with_hevy_on_adds_the_new_workout(instance: Path) -> None:
    hevy = FakeHevy(CLOCK, events=[an_updated_event(TODAYS)])

    run = coach("import", hevy=hevy)

    assert run.code == 0, run.stdout
    assert run.envelope["result"]["workouts"] == {"new": 1, "versioned": 0, "gone": 0, "back": 0}
    assert coach("status").envelope["result"]["workouts"] == {"hevy": 358, "manual": 11}


def test_import_with_hevy_off_is_skipped(instance: Path) -> None:
    config = instance / "coach.toml"
    config.write_text(config.read_text().replace("[hevy]\n", "", 1))

    run = coach("import")

    assert run.code == 0
    assert run.envelope["result"]["skipped"] is True


def test_the_export_round_trips_through_a_rebuilt_store(instance: Path) -> None:
    exported = tree(instance / "export")
    (instance / ".coach" / "coach.db").unlink()

    rebuilt_now = coach("status").envelope["result"]
    publish = coach("publish", "--dry-run").envelope["result"]

    assert rebuilt_now["workouts"] == {"hevy": 357, "manual": 11}
    assert (publish["written"], publish["deleted"]) == ([], [])
    assert tree(instance / "export") == exported
