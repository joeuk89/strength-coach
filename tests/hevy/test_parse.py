import json

import pytest
from support.hevy_fixtures import hevy_fixture

from coach.core.errors import Unreachable
from coach.core.mirror import (
    BodyMeasurement,
    ExerciseTemplate,
    Folder,
    LoggedSet,
    RoutineExercise,
    RoutineSet,
    WorkoutEvent,
)
from coach.hevy.parse import (
    parse_body_measurement_page,
    parse_exercise_template_page,
    parse_folder_page,
    parse_routine,
    parse_routine_page,
    parse_workout_events_page,
    parse_workout_page,
)


def test_a_workout_page_parses_into_workouts_with_flat_logged_sets() -> None:
    page = parse_workout_page(hevy_fixture("workout_page"))

    assert page.page_count == 1
    [workout] = page.items
    assert workout.id == "10000000-0000-4000-8000-000000000001"
    assert workout.updated_at == "2026-09-28T19:05:00.000Z"
    assert workout.title == "Session A"
    assert workout.routine_id == "00000000-0000-4000-8000-000000000001"
    assert workout.started_at == "2026-09-28T18:00:00+00:00"
    assert workout.ended_at == "2026-09-28T19:00:00+00:00"
    assert workout.notes == "felt strong"
    assert workout.sets == (
        LoggedSet(
            0,
            "F0000001",
            "Squat (Barbell)",
            "warm_up",
            "warmup",
            60.0,
            5,
            None,
            None,
            None,
            "belt on top set",
        ),
        LoggedSet(
            1, "F0000001", "Squat (Barbell)", "working", "normal", 95.0, 5, None, None, 7.5, None
        ),
        LoggedSet(
            2, "F0000001", "Squat (Barbell)", "working", "failure", 95.0, 4, None, None, 10.0, None
        ),
        LoggedSet(3, "F0000003", "Plank", "working", "normal", None, None, 60, None, None, None),
    )


def test_a_workout_keeps_its_raw_payload() -> None:
    payload = hevy_fixture("workout_page")

    [workout] = parse_workout_page(payload).items

    assert json.loads(workout.raw) == payload["workouts"][0]


def test_a_workout_events_page_holds_updates_with_their_workout_and_deletes_by_id() -> None:
    page = parse_workout_events_page(hevy_fixture("workout_events_page"))

    updated, deleted = page.items
    assert updated.kind == "updated"
    assert updated.workout_id == "10000000-0000-4000-8000-000000000002"
    assert updated.workout is not None
    assert updated.workout.routine_id is None
    assert [s.set_type for s in updated.workout.sets] == ["working"]
    assert [s.raw_set_type for s in updated.workout.sets] == ["dropset"]
    assert deleted == WorkoutEvent(
        kind="deleted",
        workout_id="10000000-0000-4000-8000-000000000009",
        workout=None,
        deleted_at="2026-10-13T09:30:00.000Z",
    )


def test_a_routine_parses_with_its_exercises_sets_and_folder() -> None:
    payload = hevy_fixture("routine")

    routine = parse_routine(payload)

    assert routine.id == "00000000-0000-4000-8000-000000000001"
    assert routine.title == "Session A"
    assert routine.folder_id == "1"
    assert routine.updated_at == "2026-10-04T19:00:00.000Z"
    assert routine.notes is None
    squat, bench = routine.exercises
    assert squat == RoutineExercise(
        index=0,
        hevy_template_id="F0000001",
        title="Squat (Barbell)",
        rest_s=180,
        notes="Target: 3x5 @ RPE 8",
        superset_id=None,
        sets=(
            RoutineSet(0, "warmup", 60.0, 5, None, None, None),
            RoutineSet(1, "normal", 97.5, 5, None, None, None),
        ),
    )
    assert bench.notes is None
    assert bench.sets == (RoutineSet(0, "normal", 22.5, None, (8, 10), None, None),)
    assert json.loads(routine.raw) == payload["routine"]


def test_a_routine_page_holds_routines() -> None:
    routine = hevy_fixture("routine")["routine"]

    page = parse_routine_page({"page": 1, "page_count": 3, "routines": [routine]})

    assert page.page_count == 3
    assert page.items == (parse_routine({"routine": routine}),)


def test_a_folder_page_parses_folders_with_text_ids() -> None:
    page = parse_folder_page(hevy_fixture("routine_folder_page"))

    assert page.items == (
        Folder(id="1", title="Program", index=0, updated_at="2026-09-01T12:00:00.000Z"),
    )


def test_an_exercise_template_page_parses_templates() -> None:
    page = parse_exercise_template_page(hevy_fixture("exercise_template_page"))

    assert page.items == (
        ExerciseTemplate(
            id="F0000001",
            title="Squat (Barbell)",
            exercise_type="weight_reps",
            primary_muscle_group="quadriceps",
            secondary_muscle_groups=("glutes", "hamstrings"),
            equipment="barbell",
            is_custom=False,
        ),
    )


def test_a_body_measurement_page_parses_dated_readings() -> None:
    page = parse_body_measurement_page(hevy_fixture("body_measurement_page"))

    assert page.items == (
        BodyMeasurement(date="2026-09-28", weight_kg=80.4, lean_mass_kg=None, fat_percent=18.5),
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"page": 1, "workouts": []},
        {"page": 1, "page_count": 1, "workouts": "none"},
        {"page": 1, "page_count": 1, "workouts": [{"id": "w"}]},
        {
            "page": 1,
            "page_count": 1,
            "workouts": [
                {
                    "id": "w",
                    "updated_at": "t",
                    "start_time": "s",
                    "exercises": [{"sets": [{"type": "normal", "reps": "five"}]}],
                }
            ],
        },
    ],
)
def test_a_payload_of_the_wrong_shape_is_hevy_unreachable(payload: object) -> None:
    with pytest.raises(Unreachable) as raised:
        parse_workout_page(payload)

    assert raised.value.code == "hevy_unreachable"
