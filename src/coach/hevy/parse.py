import json
from collections.abc import Callable
from typing import cast

from coach.core.errors import Unreachable
from coach.core.mirror import (
    BodyMeasurement,
    ExerciseTemplate,
    Folder,
    LoggedSet,
    Page,
    Routine,
    RoutineExercise,
    RoutineSet,
    SetType,
    Workout,
    WorkoutEvent,
)

type Payload = dict[str, object]


def parse_workout_page(payload: object) -> Page[Workout]:
    return _page(payload, "workouts", parse_workout)


def parse_workout_events_page(payload: object) -> Page[WorkoutEvent]:
    return _page(payload, "events", _workout_event)


def parse_routine(payload: object) -> Routine:
    """One routine as GET /v1/routines/{id} answers it, wrapped in `routine`."""
    return _routine(_mapping(payload).get("routine"))


def parse_routine_page(payload: object) -> Page[Routine]:
    return _page(payload, "routines", _routine)


def parse_folder_page(payload: object) -> Page[Folder]:
    return _page(payload, "routine_folders", parse_folder)


def parse_exercise_template_page(payload: object) -> Page[ExerciseTemplate]:
    return _page(payload, "exercise_templates", _exercise_template)


def parse_body_measurement_page(payload: object) -> Page[BodyMeasurement]:
    return _page(payload, "body_measurements", _body_measurement)


def parse_folder(payload: object) -> Folder:
    folder = _mapping(payload)
    return Folder(
        id=_text(folder, "id"),
        title=_text(folder, "title"),
        index=_optional_int(folder, "index"),
        updated_at=_optional_text(folder, "updated_at"),
    )


def parse_workout(payload: object) -> Workout:
    workout = _mapping(payload)
    sets: list[LoggedSet] = []
    for exercise in _list(workout, "exercises"):
        exercise_note = _optional_text(exercise, "notes")
        for index, logged in enumerate(_list(exercise, "sets")):
            raw_type = _text(logged, "type")
            sets.append(
                LoggedSet(
                    position=len(sets),
                    hevy_template_id=_optional_text(exercise, "exercise_template_id"),
                    hevy_title=_optional_text(exercise, "title"),
                    set_type=_set_type(raw_type),
                    raw_set_type=raw_type,
                    weight_kg=_optional_float(logged, "weight_kg"),
                    reps=_optional_int(logged, "reps"),
                    duration_s=_optional_int(logged, "duration_seconds"),
                    distance_m=_optional_float(logged, "distance_meters"),
                    rpe=_optional_float(logged, "rpe"),
                    note=exercise_note if index == 0 else None,
                )
            )
    return Workout(
        id=_text(workout, "id"),
        updated_at=_text(workout, "updated_at"),
        title=_optional_text(workout, "title"),
        routine_id=_optional_text(workout, "routine_id"),
        started_at=_text(workout, "start_time"),
        ended_at=_optional_text(workout, "end_time"),
        notes=_optional_text(workout, "description"),
        sets=tuple(sets),
        raw=_raw(workout),
    )


def _workout_event(payload: object) -> WorkoutEvent:
    event = _mapping(payload)
    kind = event.get("type")
    if kind == "updated":
        workout = parse_workout(event.get("workout"))
        return WorkoutEvent(kind="updated", workout_id=workout.id, workout=workout, deleted_at=None)
    if kind == "deleted":
        return WorkoutEvent(
            kind="deleted",
            workout_id=_text(event, "id"),
            workout=None,
            deleted_at=_optional_text(event, "deleted_at"),
        )
    raise _malformed(f"a workout event of type {kind!r}")


def _routine(payload: object) -> Routine:
    routine = _mapping(payload)
    return Routine(
        id=_text(routine, "id"),
        title=_text(routine, "title"),
        folder_id=_optional_text(routine, "folder_id"),
        updated_at=_text(routine, "updated_at"),
        notes=_optional_text(routine, "notes"),
        exercises=tuple(_routine_exercise(e) for e in _list(routine, "exercises")),
        raw=_raw(routine),
    )


def _routine_exercise(exercise: Payload) -> RoutineExercise:
    return RoutineExercise(
        index=_int(exercise, "index"),
        hevy_template_id=_text(exercise, "exercise_template_id"),
        title=_optional_text(exercise, "title"),
        rest_s=_optional_int(exercise, "rest_seconds"),
        notes=_optional_text(exercise, "notes"),
        superset_id=_optional_int(exercise, "superset_id"),
        sets=tuple(_routine_set(s) for s in _list(exercise, "sets")),
    )


def _routine_set(routine_set: Payload) -> RoutineSet:
    rep_range = routine_set.get("rep_range")
    bounds = None
    if rep_range is not None:
        span = _mapping(rep_range)
        start, end = _optional_int(span, "start"), _optional_int(span, "end")
        bounds = None if start is None or end is None else (start, end)
    return RoutineSet(
        index=_int(routine_set, "index"),
        set_type=_text(routine_set, "type"),
        weight_kg=_optional_float(routine_set, "weight_kg"),
        reps=_optional_int(routine_set, "reps"),
        rep_range=bounds,
        duration_s=_optional_int(routine_set, "duration_seconds"),
        distance_m=_optional_float(routine_set, "distance_meters"),
    )


def _exercise_template(payload: object) -> ExerciseTemplate:
    template = _mapping(payload)
    secondary: object = template.get("secondary_muscle_groups") or []
    if not isinstance(secondary, list) or not all(
        isinstance(m, str) for m in cast(list[object], secondary)
    ):
        raise _malformed("secondary_muscle_groups is not a list of text")
    return ExerciseTemplate(
        id=_text(template, "id"),
        title=_text(template, "title"),
        exercise_type=_optional_text(template, "type"),
        primary_muscle_group=_optional_text(template, "primary_muscle_group"),
        secondary_muscle_groups=tuple(cast(list[str], secondary)),
        equipment=_optional_text(template, "equipment"),
        is_custom=template.get("is_custom") is True,
    )


def _body_measurement(payload: object) -> BodyMeasurement:
    measurement = _mapping(payload)
    return BodyMeasurement(
        date=_text(measurement, "date"),
        weight_kg=_optional_float(measurement, "weight_kg"),
        lean_mass_kg=_optional_float(measurement, "lean_mass_kg"),
        fat_percent=_optional_float(measurement, "fat_percent"),
    )


def _set_type(raw_type: str) -> SetType:
    # schema.md, logged_set.set_type: Hevy's warmup is warm_up, every other Hevy type is working.
    return "warm_up" if raw_type == "warmup" else "working"


def _page[T](payload: object, key: str, parse: Callable[[object], T]) -> Page[T]:
    page = _mapping(payload)
    page_count = page.get("page_count")
    if not isinstance(page_count, int):
        raise _malformed(f"a {key} page has no page_count")
    return Page(items=tuple(parse(item) for item in _list(page, key)), page_count=page_count)


def _raw(payload: Payload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mapping(value: object) -> Payload:
    if not isinstance(value, dict):
        raise _malformed(f"expected an object, got {type(value).__name__}")
    return cast(Payload, value)


def _list(payload: Payload, key: str) -> list[Payload]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise _malformed(f"{key} is not a list")
    return [_mapping(item) for item in cast(list[object], value)]


def _text(payload: Payload, key: str) -> str:
    value = _optional_text(payload, key)
    if value is None:
        raise _malformed(f"{key} is missing")
    return value


def _optional_text(payload: Payload, key: str) -> str | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise _malformed(f"{key} is not text")
    return str(value)


def _int(payload: Payload, key: str) -> int:
    value = _optional_int(payload, key)
    if value is None:
        raise _malformed(f"{key} is missing")
    return value


def _optional_int(payload: Payload, key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value != int(value):
        raise _malformed(f"{key} is not a whole number")
    return int(value)


def _optional_float(payload: Payload, key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _malformed(f"{key} is not a number")
    return float(value)


def _malformed(detail: str) -> Unreachable:
    return Unreachable("hevy_unreachable", f"Hevy answered with an unexpected payload: {detail}")
