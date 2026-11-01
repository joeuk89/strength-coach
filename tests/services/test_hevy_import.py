import datetime
import json
from pathlib import Path

import pytest
from support.clock import NOON, FixedClock
from support.fake_hevy import FakeHevy
from support.hevy_fixtures import hevy_fixture
from support.hevy_payloads import (
    a_deleted_event,
    a_folder,
    a_measurement,
    a_routine,
    a_set,
    a_workout,
    an_exercise,
    an_updated_event,
)
from support.recording_opener import RecordingOpener, Reply

from coach.core.errors import Unreachable
from coach.hevy.client import HevyApiClient
from coach.services.hevy_import import import_hevy
from coach.store.connection import open_store
from coach.store.import_runs import import_runs, last_import_at
from coach.store.mirrors import folders, routines
from coach.store.weigh_ins import live_weigh_ins
from coach.store.workouts import current_workouts, tombstones, workout_versions

A = "10000000-0000-4000-8000-00000000000a"
B = "10000000-0000-4000-8000-00000000000b"
C = "10000000-0000-4000-8000-00000000000c"


def test_a_full_import_stores_each_workout_with_its_sets_and_raw_payload() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    squat = an_exercise("D04AC939", "Squat (Barbell)", a_set(weight_kg=100.0), a_set(reps=3))
    fake = FakeHevy(
        clock,
        workouts=[a_workout(A, exercises=[squat]), a_workout(B), a_workout(C)],
    )

    result = import_hevy(conn, fake, clock, full=True, units="kg")

    assert result.workouts.new == 3
    stored = {w.id: w for w in current_workouts(conn)}
    assert sorted(stored) == [A, B, C]
    assert [(s.position, s.hevy_template_id, s.weight_kg, s.reps) for s in stored[A].sets] == [
        (0, "D04AC939", 100.0, 5),
        (1, "D04AC939", 100.0, 3),
    ]
    assert json.loads(stored[A].raw or "")["id"] == A
    assert stored[A].source == "hevy"
    assert stored[A].date == "2026-10-26"


def test_a_second_identical_full_import_stores_nothing_and_reports_zeros() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    fake = FakeHevy(clock, workouts=[a_workout(A), a_workout(B), a_workout(C)])
    import_hevy(conn, fake, clock, full=True, units="kg")

    again = import_hevy(conn, fake, clock, full=True, units="kg")

    assert (again.workouts.new, again.workouts.versioned) == (0, 0)
    assert (again.workouts.gone, again.workouts.back) == (0, 0)
    assert [len(workout_versions(conn, w)) for w in (A, B, C)] == [1, 1, 1]


def test_an_app_edit_appends_a_version_and_the_current_view_returns_the_latest() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(
        conn,
        FakeHevy(clock, workouts=[a_workout(A, title="Session A")]),
        clock,
        full=True,
        units="kg",
    )
    edited = a_workout(A, title="Session A (edited)", updated_at="2026-10-27T08:00:00.000Z")

    result = import_hevy(conn, FakeHevy(clock, workouts=[edited]), clock, full=True, units="kg")

    assert (result.workouts.new, result.workouts.versioned) == (0, 1)
    assert [v.title for v in workout_versions(conn, A)] == ["Session A", "Session A (edited)"]
    assert [w.title for w in current_workouts(conn)] == ["Session A (edited)"]


def test_a_workout_missing_from_a_full_pull_is_gone_and_keeps_its_sets() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(
        conn, FakeHevy(clock, workouts=[a_workout(A), a_workout(B)]), clock, full=True, units="kg"
    )

    result = import_hevy(
        conn, FakeHevy(clock, workouts=[a_workout(B)]), clock, full=True, units="kg"
    )

    assert result.workouts.gone == 1
    assert [w.id for w in current_workouts(conn)] == [B]
    assert [(t.kind, t.source) for t in tombstones(conn, A)] == [("gone", "full")]
    assert len(workout_versions(conn, A)[0].sets) == 1


def test_a_delete_event_marks_the_workout_gone_with_source_event() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(conn, FakeHevy(clock, workouts=[a_workout(A)]), clock, full=True, units="kg")
    later = FixedClock(clock.moment + datetime.timedelta(days=1))
    deleted = a_deleted_event(A, utc(later.moment - datetime.timedelta(hours=1)))

    result = import_hevy(conn, FakeHevy(later, events=[deleted]), later, full=False, units="kg")

    assert (result.kind, result.workouts.gone) == ("event", 1)
    assert current_workouts(conn) == ()
    assert [(t.kind, t.source) for t in tombstones(conn, A)] == [("gone", "event")]
    assert len(workout_versions(conn, A)) == 1


def test_a_returning_workout_appends_back_reads_again_and_warns() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(conn, FakeHevy(clock, workouts=[a_workout(A)]), clock, full=True, units="kg")
    import_hevy(conn, FakeHevy(clock, workouts=[]), clock, full=True, units="kg")
    later = FixedClock(clock.moment + datetime.timedelta(hours=1))

    result = import_hevy(
        conn, FakeHevy(later, workouts=[a_workout(A)]), later, full=True, units="kg"
    )

    assert result.workouts.back == 1
    assert [t.kind for t in tombstones(conn, A)] == ["gone", "back"]
    assert [w.id for w in current_workouts(conn)] == [A]
    reappeared = [f for f in result.warnings if f.code == "workout_reappeared"]
    assert [(f.key, dict(f.params)) for f in reappeared] == [
        (
            f"workout_reappeared@workout:{A}",
            {"noticed_at": "2026-10-30T13:00:00Z", "updated_at": "2026-10-26T19:05:00Z"},
        )
    ]


def test_a_delete_then_an_edit_in_one_event_pull_keeps_the_workout_current() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(conn, FakeHevy(clock, workouts=[a_workout(A)]), clock, full=True, units="kg")
    later = FixedClock(clock.moment + datetime.timedelta(days=1))
    deleted = a_deleted_event(A, utc(later.moment - datetime.timedelta(hours=2)))
    edited = a_workout(A, updated_at=utc(later.moment - datetime.timedelta(hours=1)))
    events = [deleted, an_updated_event(edited)]

    result = import_hevy(conn, FakeHevy(later, events=events), later, full=False, units="kg")

    assert (result.workouts.versioned, result.workouts.gone, result.workouts.back) == (1, 0, 0)
    assert tombstones(conn, A) == ()
    assert [w.id for w in current_workouts(conn)] == [A]
    assert len(import_runs(conn)) == 2


def test_an_event_pull_reaches_back_ten_minutes_past_the_last_import() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(conn, FakeHevy(clock), clock, full=True, units="kg")
    later = FixedClock(clock.moment + datetime.timedelta(days=1))
    inside = a_workout(A, updated_at=utc(clock.moment - datetime.timedelta(minutes=5)))
    outside = a_workout(B, updated_at=utc(clock.moment - datetime.timedelta(minutes=15)))
    events = [an_updated_event(inside), an_updated_event(outside)]

    result = import_hevy(conn, FakeHevy(later, events=events), later, full=False, units="kg")

    assert result.since == "2026-10-30T11:50:00Z"
    assert [w.id for w in current_workouts(conn)] == [A]


def utc(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.UTC).isoformat()


def test_an_unknown_template_keeps_its_raw_id_and_title_and_warns_once_per_workout() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    custom = an_exercise("C0FFEE01", "Pallof Press (Band)")
    other = an_exercise("C0FFEE02", "Hollow Hold")
    fake = FakeHevy(clock, workouts=[a_workout(A, exercises=[custom, other]), a_workout(B)])

    result = import_hevy(conn, fake, clock, full=True, units="kg")

    stored = {w.id: w for w in current_workouts(conn)}
    assert [(s.hevy_template_id, s.hevy_title) for s in stored[A].sets] == [
        ("C0FFEE01", "Pallof Press (Band)"),
        ("C0FFEE02", "Hollow Hold"),
    ]
    unmapped = [f for f in result.warnings if f.code == "exercise_unmapped"]
    assert [(f.key, dict(f.params)) for f in unmapped] == [
        (
            f"exercise_unmapped@workout:{A}",
            {"hevy_template_id": "C0FFEE01", "title": "Pallof Press (Band)"},
        ),
        (
            f"exercise_unmapped@workout:{B}",
            {"hevy_template_id": "D04AC939", "title": "Squat (Barbell)"},
        ),
    ]


def test_hevy_warmup_lands_as_warm_up_and_every_other_set_type_as_working() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    sets = [a_set(t) for t in ("warmup", "normal", "failure", "dropset")]
    fake = FakeHevy(clock, workouts=[a_workout(A, exercises=[an_exercise("X", "Row", *sets)])])

    import_hevy(conn, fake, clock, full=True, units="kg")

    (workout,) = current_workouts(conn)
    assert [s.set_type for s in workout.sets] == ["warm_up", "working", "working", "working"]
    assert [s["type"] for s in json.loads(workout.raw or "")["exercises"][0]["sets"]] == [
        "warmup",
        "normal",
        "failure",
        "dropset",
    ]


R1 = "00000000-0000-4000-8000-0000000000r1"
R2 = "00000000-0000-4000-8000-0000000000r2"


def test_routines_are_upserted_by_hevy_id_and_never_deleted() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    first = [
        a_routine(R1, updated_at="2026-10-01T10:00:00Z"),
        a_routine(R2, updated_at="2026-10-01T10:00:00Z"),
    ]
    import_hevy(conn, FakeHevy(clock, routines=first), clock, full=True, units="kg")
    moved = a_routine(R1, title="Session A v2", updated_at="2026-10-20T10:00:00Z")

    result = import_hevy(conn, FakeHevy(clock, routines=[moved]), clock, full=True, units="kg")

    assert result.routines == 1
    assert [(r.hevy_id, r.title, r.updated_at) for r in routines(conn)] == [
        (R1, "Session A v2", "2026-10-20T10:00:00Z"),
        (R2, "Session A", "2026-10-01T10:00:00Z"),
    ]


def test_the_engine_folders_are_mirrored_by_role_and_never_deleted() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    hevy_folders = [a_folder(1, "Program"), a_folder(2, "Retired"), a_folder(3, "My stuff")]
    import_hevy(conn, FakeHevy(clock, folders=hevy_folders), clock, full=True, units="kg")

    result = import_hevy(
        conn, FakeHevy(clock, folders=[a_folder(1, "Program")]), clock, full=True, units="kg"
    )

    assert result.folders == 0
    assert [(f.role, f.hevy_id, f.title) for f in folders(conn)] == [
        ("program", "1", "Program"),
        ("retired", "2", "Retired"),
    ]


def test_two_folders_sharing_an_engine_title_are_not_mirrored() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    hevy_folders = [a_folder(1, "Program"), a_folder(2, "Program")]

    import_hevy(conn, FakeHevy(clock, folders=hevy_folders), clock, full=True, units="kg")

    assert folders(conn) == ()


def test_body_measurements_become_hevy_weigh_ins_once() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    measured = [a_measurement("2026-10-20", 80.4), a_measurement("2026-10-27", None)]
    import_hevy(conn, FakeHevy(clock, measurements=measured), clock, full=True, units="kg")

    again = import_hevy(conn, FakeHevy(clock, measurements=measured), clock, full=True, units="kg")

    assert again.weigh_ins == 0
    assert [(w.id, w.date, w.kg, w.source) for w in live_weigh_ins(conn)] == [
        ("wi-0001", "2026-10-20", 80.4, "hevy")
    ]


def test_a_changed_measurement_withdraws_the_old_weigh_in_and_enters_the_new() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    import_hevy(
        conn,
        FakeHevy(clock, measurements=[a_measurement("2026-10-20", 80.4)]),
        clock,
        full=True,
        units="kg",
    )

    corrected = [a_measurement("2026-10-20", 80.9)]
    result = import_hevy(
        conn, FakeHevy(clock, measurements=corrected), clock, full=True, units="kg"
    )

    assert result.weigh_ins == 1
    assert [(w.date, w.kg) for w in live_weigh_ins(conn)] == [("2026-10-20", 80.9)]


def test_an_unreachable_hevy_writes_nothing() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    fake = FakeHevy(
        clock, workouts=[a_workout(A)], routines=[a_routine(R1, updated_at="2026-10-01T10:00:00Z")]
    )
    fake.fail_next_get()

    with pytest.raises(Unreachable):
        import_hevy(conn, fake, clock, full=True, units="kg")

    assert (current_workouts(conn), routines(conn), last_import_at(conn)) == ((), (), None)


EIGHT_DAYS_AGO = NOON - datetime.timedelta(days=8)


def test_an_unreachable_hevy_after_a_week_without_an_import_warns_snapshot_stale() -> None:
    conn = open_store(":memory:")
    import_hevy(
        conn,
        FakeHevy(FixedClock(EIGHT_DAYS_AGO)),
        FixedClock(EIGHT_DAYS_AGO),
        full=True,
        units="kg",
    )
    clock = FixedClock()
    fake = FakeHevy(clock)
    fake.fail_next_get()

    with pytest.raises(Unreachable) as raised:
        import_hevy(conn, fake, clock, full=False, units="kg")

    assert raised.value.code == "hevy_unreachable"
    assert [(w.code, w.params) for w in raised.value.warnings] == [
        ("snapshot_stale", {"last_import": "2026-10-22", "age_limit_days": 7}),
    ]


def test_an_unreachable_hevy_inside_the_week_raises_no_snapshot_stale() -> None:
    conn = open_store(":memory:")
    recent = NOON - datetime.timedelta(days=3)
    import_hevy(conn, FakeHevy(FixedClock(recent)), FixedClock(recent), full=True, units="kg")
    clock = FixedClock()
    fake = FakeHevy(clock)
    fake.fail_next_get()

    with pytest.raises(Unreachable) as raised:
        import_hevy(conn, fake, clock, full=False, units="kg")

    assert raised.value.warnings == ()


def test_an_import_after_a_week_closes_the_gap_and_raises_no_snapshot_stale() -> None:
    conn = open_store(":memory:")
    import_hevy(
        conn,
        FakeHevy(FixedClock(EIGHT_DAYS_AGO)),
        FixedClock(EIGHT_DAYS_AGO),
        full=True,
        units="kg",
    )
    clock = FixedClock()

    result = import_hevy(conn, FakeHevy(clock), clock, full=False, units="kg")

    assert [w.code for w in result.warnings] == []


def test_an_import_records_its_run_with_a_summary() -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    fake = FakeHevy(
        clock, workouts=[a_workout(A)], measurements=[a_measurement("2026-10-20", 80.4)]
    )

    import_hevy(conn, fake, clock, full=True, units="kg")

    (run,) = import_runs(conn)
    assert (run.id, run.at, run.since, run.kind) == (
        "ir-0001",
        "2026-10-30T12:00:00Z",
        None,
        "full",
    )
    assert run.summary == {
        "workout": 1,
        "logged_set": 1,
        "tombstone": 0,
        "weigh_in": 1,
        "routine": 0,
        "folder": 0,
    }


def test_an_import_through_the_real_client_sends_only_gets(tmp_path: Path) -> None:
    conn = open_store(":memory:")
    clock = FixedClock()
    pages = ("workout_page", "routine_folder_page", "body_measurement_page")
    workouts, folder_page, measurements = (hevy_fixture(name) for name in pages)
    routine_page = {"page": 1, "page_count": 1, "routines": [hevy_fixture("routine")["routine"]]}
    events = hevy_fixture("workout_events_page")
    script = [workouts, routine_page, folder_page, measurements]
    script += [events, routine_page, folder_page, measurements]
    opener = RecordingOpener(Reply(200, page) for page in script)
    client = HevyApiClient("k", tmp_path / "writes.jsonl", clock, opener=opener)

    import_hevy(conn, client, clock, full=True, units="kg")
    import_hevy(conn, client, clock, full=False, units="kg")

    assert {s.method for s in opener.sent} == {"GET"}
    assert any("/v1/workouts/events" in s.url for s in opener.sent)
    assert not (tmp_path / "writes.jsonl").exists()
