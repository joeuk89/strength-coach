import datetime
import json
from pathlib import Path
from typing import Any

import pytest
from support.clock import FixedClock
from support.fake_hevy import FakeHevy
from support.hevy_fixtures import hevy_fixture
from support.recording_opener import RecordingOpener, RecordingSleeper, Reply

from coach.core.errors import Unreachable
from coach.hevy.client import HevyApiClient
from coach.hevy.parse import (
    parse_body_measurement_page,
    parse_exercise_template_page,
    parse_folder_page,
    parse_routine,
    parse_workout_events_page,
    parse_workout_page,
)
from coach.hevy.protocol import HevyClient, WriteContext

ROUTINE_ID = "00000000-0000-4000-8000-000000000001"
CONTEXT = WriteContext("wp-2026-w44", "h-abc", ROUTINE_ID)
PUT_BODY: dict[str, Any] = {
    "routine": {
        "title": "Session A",
        "folder_id": 1,
        "notes": "Week 3 of 4",
        "exercises": [
            {
                "exercise_template_id": "F0000001",
                "superset_id": None,
                "rest_seconds": 180,
                "notes": "Week 3 of 4\nTarget: 3x5",
                "sets": [{"type": "normal", "weight_kg": 100.0, "reps": 5}],
            }
        ],
    }
}


def a_fake(clock: FixedClock | None = None) -> FakeHevy:
    return FakeHevy(
        clock or FixedClock(),
        workouts=hevy_fixture("workout_page")["workouts"],
        events=hevy_fixture("workout_events_page")["events"],
        routines=[hevy_fixture("routine")["routine"]],
        folders=hevy_fixture("routine_folder_page")["routine_folders"],
        templates=hevy_fixture("exercise_template_page")["exercise_templates"],
        measurements=hevy_fixture("body_measurement_page")["body_measurements"],
    )


def protocol_members() -> set[str]:
    return {name for name in vars(HevyClient) if not name.startswith("_")}


FAULT_CONTROLS = {"audit", "move_routine", "fail_next_get", "differ_next_read_back"}


def test_the_fake_has_the_protocol_and_its_fault_controls_and_nothing_more() -> None:
    fake = a_fake()
    client: HevyClient = fake

    public = {name for name in dir(client) if not name.startswith("_")}

    assert public == protocol_members() | FAULT_CONTROLS
    assert {"delete_routine", "create_workout", "update_workout", "request"} & public == set()


def test_every_fixture_payload_parses_to_the_value_the_fake_returns() -> None:
    fake = a_fake()
    long_ago = datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC)

    assert fake.workouts() == parse_workout_page(hevy_fixture("workout_page")).items
    assert (
        fake.workout_events(long_ago)
        == parse_workout_events_page(hevy_fixture("workout_events_page")).items
    )
    assert fake.routines() == (parse_routine(hevy_fixture("routine")),)
    assert fake.routine(ROUTINE_ID) == parse_routine(hevy_fixture("routine"))
    assert fake.folders() == parse_folder_page(hevy_fixture("routine_folder_page")).items
    assert (
        fake.exercise_templates()
        == parse_exercise_template_page(hevy_fixture("exercise_template_page")).items
    )
    assert (
        fake.body_measurements()
        == parse_body_measurement_page(hevy_fixture("body_measurement_page")).items
    )


def test_workout_events_since_a_moment_leave_out_older_events() -> None:
    fake = a_fake()

    events = fake.workout_events(datetime.datetime(2026, 10, 12, 12, 0, tzinfo=datetime.UTC))

    assert [e.kind for e in events] == ["deleted"]


def test_a_routine_put_loses_the_routine_level_note_and_moves_updated_at() -> None:
    later = FixedClock(datetime.datetime(2026, 11, 2, 7, 30, tzinfo=datetime.UTC))
    fake = a_fake(later)

    written = fake.update_routine(ROUTINE_ID, PUT_BODY, CONTEXT)

    assert written.notes is None
    assert written.updated_at == "2026-11-02T07:30:00+00:00"
    [squat] = written.exercises
    assert squat.notes == "Week 3 of 4\nTarget: 3x5"
    assert squat.title == "Squat (Barbell)"
    assert [(s.weight_kg, s.reps) for s in squat.sets] == [(100.0, 5)]
    assert fake.routine(ROUTINE_ID) == written


def test_a_routine_post_keeps_its_note_and_gets_a_new_id() -> None:
    fake = a_fake()

    first = fake.create_routine(PUT_BODY, CONTEXT)
    second = fake.create_routine(PUT_BODY, CONTEXT)

    assert first.notes == "Week 3 of 4"
    assert len({first.id, second.id, ROUTINE_ID}) == 3
    assert {r.id for r in fake.routines()} == {first.id, second.id, ROUTINE_ID}


def test_a_folder_and_a_template_post_add_to_what_the_fake_lists() -> None:
    fake = a_fake()

    folder = fake.create_folder({"routine_folder": {"title": "Retired"}}, CONTEXT)
    template_id = fake.create_exercise_template(
        {
            "exercise": {
                "title": "Sled Push",
                "exercise_type": "distance_duration",
                "equipment_category": "other",
                "muscle_group": "full_body",
                "other_muscles": [],
            }
        },
        CONTEXT,
    )

    assert folder in fake.folders()
    assert folder.title == "Retired"
    [sled] = [t for t in fake.exercise_templates() if t.id == template_id]
    assert (sled.title, sled.exercise_type, sled.equipment, sled.is_custom) == (
        "Sled Push",
        "distance_duration",
        "other",
        True,
    )


def test_a_moved_routine_reads_with_the_new_updated_at() -> None:
    fake = a_fake()

    fake.move_routine(ROUTINE_ID, "2026-10-29T08:00:00.000Z")

    assert fake.routine(ROUTINE_ID).updated_at == "2026-10-29T08:00:00.000Z"


def test_a_failed_get_is_hevy_unreachable_once() -> None:
    fake = a_fake()

    fake.fail_next_get()

    with pytest.raises(Unreachable) as raised:
        fake.routines()
    assert raised.value.code == "hevy_unreachable"
    assert len(fake.routines()) == 1


def test_a_read_back_records_a_verify_line_and_can_be_made_to_differ() -> None:
    fake = a_fake()
    fake.update_routine(ROUTINE_ID, PUT_BODY, CONTEXT)
    sent = fake.routine(ROUTINE_ID)

    def diff(live: Any) -> tuple[str, ...]:
        return () if live == sent else ("read-back differs",)

    matched = fake.read_back(ROUTINE_ID, CONTEXT, diff)
    fake.differ_next_read_back()
    differed = fake.read_back(ROUTINE_ID, CONTEXT, diff)

    assert matched.verified
    assert not differed.verified
    assert fake.routine(ROUTINE_ID) == sent
    assert [(line["kind"], line.get("verified")) for line in fake.audit] == [
        ("request", None),
        ("response", None),
        ("verify", True),
        ("verify", False),
    ]


def test_the_fake_keeps_the_audit_lines_the_real_client_writes(tmp_path: Path) -> None:
    clock = FixedClock()
    fake = a_fake(clock)
    answer = Reply(200, {"routine_folder": {"id": 9, "index": 1, "title": "Standing"}})
    real = HevyApiClient(
        "k" * 36,
        tmp_path / "writes.jsonl",
        clock,
        opener=RecordingOpener([answer]),
        sleeper=RecordingSleeper(),
    )
    body: dict[str, object] = {"routine_folder": {"title": "Standing"}}

    fake.create_folder(body, CONTEXT)
    real.create_folder(body, CONTEXT)

    written = [json.loads(line) for line in (tmp_path / "writes.jsonl").read_text().splitlines()]
    assert fake.audit == written


def test_open_audit_succeeds_on_the_fake() -> None:
    fake = a_fake()

    fake.open_audit()

    assert fake.audit == []
