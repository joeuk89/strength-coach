import datetime
from typing import cast

from support.check_in_cards import FIRST_SUNDAY, field_of, opened
from support.closed_weeks import a_planned_squat_week, monday
from support.history import an_annotation
from support.ledger import RECORDED_AT
from support.plans import SQUAT_LINE, SQUAT_TEMPLATE, a_frozen_prescription, a_squat_program
from support.program_drafts import a_line, a_session

from coach.core.units import KG_PER_LB
from coach.store import workouts
from coach.store.connection import Connection

PLANK_TEMPLATE = "C6C9B8A0"


def a_planned_lower_week() -> Connection:
    """`lower` on Monday: the squat at 4×6–8 @8, then a `hold` plank at 2×20 s."""
    plank = a_line(
        "plank", sets=[{"count": 2, "duration_s": 20}], scheme={"name": "hold"}, start_load=None
    )
    conn = a_squat_program(a_session("lower", SQUAT_LINE, plank))
    plan_id = a_planned_squat_week(conn, monday(0))
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        monday(0),
        "plank",
        set_groups=[{"type": "working", "count": 2, "duration_s": 20}],
        change="held",
    )
    return conn


def lower_logged(conn: Connection, *plank: int, on: str = monday(0)) -> None:
    """Four squat sets of 120 lb × 8 @8, then plank sets of the seconds given."""
    logged = [(SQUAT_TEMPLATE, 120 * KG_PER_LB, 8, None, 8.0)] * 4
    logged += [(PLANK_TEMPLATE, None, None, seconds, None) for seconds in plank]
    sets = [
        workouts.SetRow(
            position=position,
            hevy_template_id=template,
            hevy_title=None,
            set_type="working",
            weight_kg=kg,
            reps=reps,
            duration_s=seconds,
            rpe=rpe,
        )
        for position, (template, kg, reps, seconds, rpe) in enumerate(logged)
    ]
    with conn:
        workouts.insert(
            conn,
            workouts.WorkoutRow(
                id="h-1",
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
            sets,
        )


def lift_rows(conn: Connection, on: datetime.date = FIRST_SUNDAY) -> dict[str, dict[str, object]]:
    rows = cast(list[dict[str, object]], field_of(opened(conn, on), "lifts").facts["rows"])
    return {str(r["exercise"]): r for r in rows}


def test_a_timed_line_shows_its_logged_seconds_beside_the_prescribed_seconds() -> None:
    conn = a_planned_lower_week()
    lower_logged(conn, 22, 18)

    plank = lift_rows(conn)["plank"]

    assert (plank["seconds"], plank["prescribed_seconds"]) == ([22, 18], 20)


def test_a_timed_line_matched_into_the_week_before_its_date_shows_the_prescribed_seconds() -> None:
    conn = a_planned_lower_week()
    lower_logged(conn, 22, 18, on=monday(1))
    an_annotation(
        conn, "a-1", "match", "workout:h-1", planned_session=f"planned_session:{monday(0)}/lower"
    )

    plank = lift_rows(conn, FIRST_SUNDAY + datetime.timedelta(days=7))["plank"]

    assert plank["prescribed_seconds"] == 20


def test_a_rep_based_lift_row_keeps_its_fields() -> None:
    conn = a_planned_lower_week()
    lower_logged(conn, 22, 18)

    squat = lift_rows(conn)["bb_back_squat"]

    assert set(squat) == {
        "exercise",
        "priority",
        "top_set",
        "e1rm",
        "e1rm_before",
        "exposures",
        "e1rm_from",
    }
