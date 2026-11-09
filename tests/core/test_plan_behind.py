import datetime

from coach.core.plan_behind import ApprovedPlan, plan_behind_program

MONDAY = datetime.date(2026, 11, 2)
PLAN = ApprovedPlan("wp-2026-11-02", MONDAY, approved_under="pv-1")


def test_a_plan_approved_under_an_older_version_is_behind_the_version_in_force() -> None:
    (flag,) = plan_behind_program(PLAN, "pv-2")

    assert flag.key == "plan_behind_program@week:2026-11-02"
    assert flag.severity == "warning"
    assert flag.params == {
        "plan_id": "wp-2026-11-02",
        "approved_under": "pv-1",
        "version_id": "pv-2",
    }
    assert flag.rn is None
    assert "redraft the week" in flag.message


def test_a_plan_approved_before_any_version_is_behind_the_first() -> None:
    (flag,) = plan_behind_program(ApprovedPlan("wp-2026-11-02", MONDAY, None), "pv-1")

    assert flag.params["approved_under"] is None
    assert flag.params["version_id"] == "pv-1"


def test_a_plan_approved_under_the_version_in_force_is_not_behind() -> None:
    assert plan_behind_program(PLAN, "pv-1") == ()


def test_no_plan_or_no_version_raises_nothing() -> None:
    assert plan_behind_program(None, "pv-2") == ()
    assert plan_behind_program(PLAN, None) == ()


def test_the_params_hash_moves_only_with_the_plan_or_the_version() -> None:
    (first,) = plan_behind_program(PLAN, "pv-2")
    (again,) = plan_behind_program(ApprovedPlan("wp-2026-11-02", MONDAY, "pv-1"), "pv-2")
    (newer,) = plan_behind_program(PLAN, "pv-3")
    (other_plan,) = plan_behind_program(ApprovedPlan("wp-2026-11-02-2", MONDAY, "pv-1"), "pv-2")

    assert first.params_hash == again.params_hash
    assert newer.params_hash != first.params_hash
    assert other_plan.params_hash != first.params_hash
