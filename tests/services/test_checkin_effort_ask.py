from collections.abc import Sequence

from support.check_in_cards import field_of, opened
from support.closed_weeks import a_planned_squat_week, monday
from support.history import an_annotation
from support.ledger import RECORDED_AT
from support.plans import SQUAT_LINE, SQUAT_TEMPLATE, a_frozen_prescription, a_squat_program
from support.program_drafts import a_line, a_session

from coach.core.check_in_card import Ask
from coach.core.units import KG_PER_LB
from coach.store import exercises, workouts
from coach.store.connection import Connection

CARRY_TEMPLATE = "F00DCA22"
CARRY = {
    "name": "Farmer's carry",
    "load_mode": "per_hand_x2",
    "equipment_kind": "dumbbell",
    "pattern": "carry",
    "muscles": {"primary": ["forearms"], "secondary": []},
    "hevy_title": "Farmer's Carry (Timed)",
    "hevy_exercise_type": "weight_duration",
    "hevy_equipment": "dumbbell",
    "hevy_muscle_group": "forearms",
}


def a_planned_carry_week() -> Connection:
    """`lower` on Monday: the squat at 4×6–8 @8, then a timed-load carry at 3×30 s @8, 40 lb."""
    carry = a_line(
        "farmers_carry",
        sets=[{"count": 3, "duration_s": 30, "rpe": 8}],
        scheme={"name": "timed_load"},
        start_load=40,
    )
    conn = a_squat_program(a_session("lower", SQUAT_LINE, carry), exercise={"farmers_carry": CARRY})
    with conn:
        exercises.update(conn, "farmers_carry", {"hevy_template_id": CARRY_TEMPLATE})
    plan_id = a_planned_squat_week(conn, monday(0))
    a_frozen_prescription(
        conn,
        plan_id,
        "lower",
        monday(0),
        "farmers_carry",
        set_groups=[{"type": "working", "count": 3, "duration_s": 30, "rpe": 8, "load": 40}],
        change="first prescription",
    )
    return conn


def carry_logged(conn: Connection, *carry: tuple[int, float | None]) -> None:
    """Four squat sets of 120 lb × 8 @8, then carry sets of (seconds, rpe) at 40 lb a hand."""
    logged = [(SQUAT_TEMPLATE, 120 * KG_PER_LB, 8, None, 8.0)] * 4
    logged += [(CARRY_TEMPLATE, 80 * KG_PER_LB, None, s, rpe) for s, rpe in carry]
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
                updated_at=f"{monday(0)}T18:00:00+00:00",
                source="hevy",
                date=monday(0),
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


def lift_asks(conn: Connection) -> Sequence[Ask]:
    return [a for a in field_of(opened(conn), "lifts").asks if a.kind != "soreness_and_niggles"]


def test_a_timed_load_line_logged_with_no_effort_asks_it_once_quoting_load_sets_and_seconds() -> (
    None
):
    conn = a_planned_carry_week()
    carry_logged(conn, (30, None), (31, None), (30, None))

    assert lift_asks(conn) == [
        Ask(
            "lift_doubt",
            "exercise:farmers_carry",
            reason="effort_missing",
            params={
                "exposures": [
                    {
                        "session": "lower",
                        "date": monday(0),
                        "repair": "workout:h-1/farmers_carry",
                        "logged": [
                            {"position": p, "load": 40.0, "reps": None, "rpe": None, "seconds": s}
                            for p, s in ((4, 30), (5, 31), (6, 30))
                        ],
                        "prescribed": [
                            {"reps": None, "reps_top": None, "rpe": 8, "load": 40, "seconds": 30}
                        ]
                        * 3,
                    }
                ]
            },
        )
    ]


def test_a_timed_load_line_whose_effort_is_stored_by_repair_asks_nothing() -> None:
    conn = a_planned_carry_week()
    carry_logged(conn, (30, None), (31, None), (30, None))
    for n, position in enumerate((4, 5, 6), start=1):
        an_annotation(
            conn,
            f"a-{n}",
            "repair",
            "workout:h-1/farmers_carry",
            position=position,
            field="rpe",
            value=8,
        )

    assert lift_asks(conn) == []


def test_a_lift_whose_sets_carry_an_rpe_gets_no_effort_ask() -> None:
    conn = a_planned_carry_week()
    carry_logged(conn, (30, 8), (30, 8), (30, 9))

    assert lift_asks(conn) == []
