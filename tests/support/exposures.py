"""Exposure values for core tests: one working set per (load, reps, rpe)."""

import datetime

from coach.core.exposure import Exposure, ExposureSet, Matched
from coach.core.load import Load, LoadMode

type Logged = tuple[float | None, int, float | None]


def an_exposure(
    on: str,
    *sets: Logged,
    workout_id: str | None = None,
    exercise_id: str = "bb_bench_press",
    mode: LoadMode = "total",
    session_id: str | None = None,
    light_week: bool = False,
) -> Exposure:
    return Exposure(
        workout_id=workout_id or f"w-{on}",
        exercise_id=exercise_id,
        date=datetime.date.fromisoformat(on),
        sets=tuple(
            ExposureSet(
                position=i,
                set_type="working",
                load=None if load is None else Load(load, mode),
                reps=reps,
                rpe=rpe,
            )
            for i, (load, reps, rpe) in enumerate(sets)
        ),
        match=None if session_id is None else Matched(session_id, light_week),
    )
