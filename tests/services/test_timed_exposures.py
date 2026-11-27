from support.ledger import RECORDED_AT, a_store, an_exercise

from coach.services.query import exposures
from coach.store import workouts
from coach.store.connection import Connection

HANG = "D1A2B3C4"
WALK = "E5F6A7B8"
BENCH = "79D0BB3A"

type Logged = tuple[str, float | None, int | None, int | None, float | None]


def a_library() -> Connection:
    conn = a_store()
    an_exercise(conn, "dead_hang", hevy_template_id=HANG, load_mode="duration")
    an_exercise(conn, "sled_push", hevy_template_id=WALK, load_mode="distance")
    an_exercise(conn, "bb_bench_press", hevy_template_id=BENCH)
    return conn


def logged(conn: Connection, id_: str, on: str, *sets: Logged) -> None:
    """Hevy sets of (template, kg, reps, seconds, metres)."""
    rows = [
        workouts.SetRow(
            position=position,
            hevy_template_id=template,
            hevy_title=None,
            set_type="working",
            weight_kg=kg,
            reps=reps,
            duration_s=seconds,
            distance_m=metres,
            rpe=None,
        )
        for position, (template, kg, reps, seconds, metres) in enumerate(sets)
    ]
    with conn:
        workouts.insert(
            conn,
            workouts.WorkoutRow(
                id=id_,
                updated_at=f"{on}T18:00:00+00:00",
                source="hevy",
                date=on,
                title=None,
                routine_id=None,
                session_id=None,
                minutes=None,
                session_rpe=None,
                notes=None,
                raw="{}",
                check_in=None,
                draft_hash=None,
                recorded_at=RECORDED_AT,
            ),
            rows,
        )


def row_of(conn: Connection, exercise: str) -> dict[str, object]:
    (row,) = exposures(conn, exercises=(exercise,), since=None, last=None, units="kg").rows
    return row


def test_a_timed_exposure_shows_the_seconds_of_each_set() -> None:
    conn = a_library()
    logged(conn, "h-1", "2026-11-14", (HANG, None, None, 22, None), (HANG, None, None, 18, None))

    row = row_of(conn, "dead_hang")

    assert (row["duration_s"], row["reps"], row["rpe"]) == ([22, 18], [None, None], [None, None])
    assert "distance_m" not in row


def test_a_distance_exposure_shows_the_metres_of_each_set() -> None:
    conn = a_library()
    logged(conn, "h-1", "2026-11-14", (WALK, None, None, None, 20.0), (WALK, None, None, None, 15.5))

    row = row_of(conn, "sled_push")

    assert row["distance_m"] == [20.0, 15.5]
    assert "duration_s" not in row
