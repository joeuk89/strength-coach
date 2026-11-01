from coach.core.flag import Flag, Scope, raise_flag
from coach.store.connection import Connection
from coach.store.workouts import unmapped_sets


def exercise_unmapped(conn: Connection) -> list[Flag]:
    """One `exercise_unmapped` per current workout carrying a template no Exercise carries,
    naming its first such set (cutover.md, "Exercise resolution on read")."""
    flags: dict[str, Flag] = {}
    for found in unmapped_sets(conn):
        if found.workout_id not in flags:
            flags[found.workout_id] = raise_flag(
                "exercise_unmapped",
                Scope("workout", workout_id=found.workout_id),
                {"hevy_template_id": found.hevy_template_id, "title": found.hevy_title},
                f"workout {found.workout_id} logs {found.hevy_title or found.hevy_template_id}, "
                "which no library Exercise carries; map it with an [[exercise]] row",
            )
    return list(flags.values())
