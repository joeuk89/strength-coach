import datetime

from coach.core.import_flags import exercise_unmapped
from coach.core.log import StoredSet, WorkoutVersion

NOW = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=datetime.UTC)


def a_set(template_id: str | None, title: str) -> StoredSet:
    return StoredSet(0, template_id, title, "working", 100.0, 5, None, None, None, None)


def a_version(workout_id: str, *sets: StoredSet) -> WorkoutVersion:
    return WorkoutVersion(
        workout_id, "2026-10-26T19:05:00Z", "hevy", "2026-10-26", None, None, 60, None, "{}", sets
    )


def test_a_mapping_heals_every_workout_carrying_the_template() -> None:
    workouts = [a_version("w1", a_set("C0FFEE01", "Hollow Hold")), a_version("w2")]
    workouts.append(a_version("w3", a_set("C0FFEE01", "Hollow Hold")))

    assert [f.key for f in exercise_unmapped(workouts, frozenset())] == [
        "exercise_unmapped@workout:w1",
        "exercise_unmapped@workout:w3",
    ]
    assert exercise_unmapped(workouts, frozenset({"C0FFEE01"})) == ()


def test_a_set_with_no_template_id_is_not_unmapped() -> None:
    assert exercise_unmapped([a_version("w1", a_set(None, "Walk"))], frozenset()) == ()
