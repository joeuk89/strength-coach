import datetime
from dataclasses import dataclass

from coach.core.flag import Flag, Scope, raise_flag


@dataclass(frozen=True)
class PlanUnder:
    """A WeekPlan with the Program version in force when it was approved, if any was."""

    id: str
    monday: datetime.date
    approved_under: str | None


def plan_behind_program(plan: PlanUnder | None, version_id: str | None) -> tuple[Flag, ...]:
    if plan is None or version_id is None or plan.approved_under == version_id:
        return ()
    flag = raise_flag(
        "plan_behind_program",
        Scope("week", plan.monday),
        {"plan_id": plan.id, "approved_under": plan.approved_under, "version_id": version_id},
        f"the plan for this week ({plan.id}) was approved under the previous program; "
        f"redraft the week to apply {version_id}",
    )
    return (flag,)
