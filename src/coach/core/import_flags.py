import datetime
from collections.abc import Collection, Iterable, Sequence

from coach.core.flag import Flag, Scope, raise_flag
from coach.core.log import WorkoutVersion
from coach.core.routine_projection import drift_class

# research-notes.md: a plan reads last week's exposures, so a mirror older than a week is stale.
SNAPSHOT_AGE_LIMIT_DAYS = 7


def workout_reappeared(workout_id: str, noticed_at: str, updated_at: str) -> Flag:
    return raise_flag(
        "workout_reappeared",
        Scope("workout", workout_id=workout_id),
        {"noticed_at": noticed_at, "updated_at": updated_at},
        f"workout {workout_id} came back from Hevy at {noticed_at} and reads again",
    )


def exercise_unmapped(
    workouts: Iterable[WorkoutVersion], mapped_template_ids: Collection[str]
) -> tuple[Flag, ...]:
    """One flag per workout carrying a template id no Exercise has (cutover.md)."""
    flags: list[Flag] = []
    for workout in workouts:
        unmapped = {
            s.hevy_template_id: s.hevy_title
            for s in workout.sets
            if s.hevy_template_id and s.hevy_template_id not in mapped_template_ids
        }
        if not unmapped:
            continue
        template_id, title = next(iter(unmapped.items()))
        titles = ", ".join(f"{t or '?'} ({i})" for i, t in unmapped.items())
        flags.append(
            raise_flag(
                "exercise_unmapped",
                Scope("workout", workout_id=workout.id),
                {"hevy_template_id": template_id, "title": title},
                f"workout {workout.id} on {workout.date} uses templates no Exercise maps: {titles}",
            )
        )
    return tuple(flags)


def snapshot_stale(last_import: datetime.datetime | None, now: datetime.datetime) -> Flag | None:
    if last_import is None or now - last_import <= datetime.timedelta(SNAPSHOT_AGE_LIMIT_DAYS):
        return None
    return raise_flag(
        "snapshot_stale",
        Scope("instance"),
        {"last_import": last_import.date().isoformat(), "age_limit_days": SNAPSHOT_AGE_LIMIT_DAYS},
        f"the last Hevy import was {(now - last_import).days} days ago; run `coach import`",
    )


def routine_drift(routine_id: str, plan_id: str, diff: Sequence[str]) -> Flag:
    found = drift_class(diff)
    return raise_flag(
        "routine_drift",
        Scope("routine", routine_id=routine_id),
        {"drift_class": found, "plan_in_force": plan_id, "diff": list(diff)},
        f"routine {routine_id} differs from {plan_id} in Hevy ({found}: {', '.join(diff)}); "
        "an override on the next WeekPlan or the next push resolves it",
    )
