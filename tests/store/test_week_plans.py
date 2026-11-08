from support.plans import a_squat_program

from coach.store import week_plans

PLAN = "wp-2026-11-02"


def a_line_row(exercise_id: str, position: int, *, on: str = "2026-11-02") -> dict[str, object]:
    return {
        "session_id": "lower",
        "date": on,
        "exercise_id": exercise_id,
        "position": position,
        "set_groups": "[]",
        "derived_from": "start_load",
        "steps": "[]",
        "flags": "[]",
        "change": "first prescription",
    }


def test_a_plans_rows_come_back_by_date_then_position_as_they_were_written() -> None:
    conn = a_squat_program()
    with conn:
        week_plans.approve(
            conn,
            {
                "id": PLAN,
                "week": "2026-11-02",
                "position": "A",
                "approved_at": "2026-11-01T08:00:00Z",
                "write_plan_hash": "sha256:w",
                "draft_hash": "sha256:d",
                "recorded_at": "2026-11-01T08:00:00Z",
            },
            supersedes=None,
            overrides=[],
            prescriptions=[
                a_line_row("bb_bench_press", 1),
                a_line_row("bb_back_squat", 2),
                a_line_row("ab_wheel", 3),
                a_line_row("bb_overhead_press", 1, on="2026-11-05"),
                a_line_row("ab_wheel", 2, on="2026-11-05"),
            ],
            acknowledgements=[],
        )

    found = week_plans.prescriptions(conn, PLAN)

    assert [(r["date"], r["exercise_id"], r["position"]) for r in found] == [
        ("2026-11-02", "bb_bench_press", 1),
        ("2026-11-02", "bb_back_squat", 2),
        ("2026-11-02", "ab_wheel", 3),
        ("2026-11-05", "bb_overhead_press", 1),
        ("2026-11-05", "ab_wheel", 2),
    ]
