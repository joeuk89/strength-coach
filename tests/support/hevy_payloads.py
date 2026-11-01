from typing import Any

type Json = dict[str, Any]


def a_set(set_type: str = "normal", *, weight_kg: float | None = 100.0, reps: int = 5) -> Json:
    return {
        "index": 0,
        "type": set_type,
        "weight_kg": weight_kg,
        "reps": reps,
        "distance_meters": None,
        "duration_seconds": None,
        "rpe": None,
        "custom_metric": None,
    }


def an_exercise(template_id: str, title: str, *sets: Json) -> Json:
    return {
        "index": 0,
        "title": title,
        "notes": "",
        "exercise_template_id": template_id,
        "superset_id": None,
        "sets": list(sets) or [a_set()],
    }


def a_workout(
    workout_id: str,
    *,
    updated_at: str = "2026-10-26T19:05:00.000Z",
    start: str = "2026-10-26T18:00:00+00:00",
    end: str = "2026-10-26T19:00:00+00:00",
    title: str = "Session A",
    exercises: list[Json] | None = None,
) -> Json:
    return {
        "id": workout_id,
        "title": title,
        "routine_id": None,
        "description": "",
        "start_time": start,
        "end_time": end,
        "updated_at": updated_at,
        "created_at": updated_at,
        "exercises": exercises or [an_exercise("D04AC939", "Squat (Barbell)")],
    }


def an_updated_event(workout: Json) -> Json:
    return {"type": "updated", "workout": workout}


def a_deleted_event(workout_id: str, deleted_at: str) -> Json:
    return {"type": "deleted", "id": workout_id, "deleted_at": deleted_at}


def a_routine(routine_id: str, *, title: str = "Session A", updated_at: str) -> Json:
    return {
        "id": routine_id,
        "title": title,
        "folder_id": 1,
        "notes": None,
        "updated_at": updated_at,
        "created_at": updated_at,
        "exercises": [],
    }


def a_folder(folder_id: int, title: str) -> Json:
    return {
        "id": folder_id,
        "index": 0,
        "title": title,
        "updated_at": "2026-09-01T12:00:00.000Z",
        "created_at": "2026-09-01T12:00:00.000Z",
    }


def a_measurement(date: str, weight_kg: float | None) -> Json:
    return {"date": date, "weight_kg": weight_kg, "lean_mass_kg": None, "fat_percent": None}
