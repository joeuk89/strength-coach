from dataclasses import dataclass
from typing import Literal, get_args

from coach.core.registries.registry import Registry, Row, terms

type Reason = Literal[
    "pain", "kit", "stall", "fatigue", "schedule", "athlete_request", "coach_judgement"
]

REASONS = terms("reasons", *get_args(Reason.__value__))


@dataclass(frozen=True)
class DecisionKind:
    name: str
    params: tuple[str, ...]
    until: Literal["required", "optional", "none"]

    def describe(self) -> Row:
        return {"name": self.name, "params": list(self.params), "until": self.until}


# docs/spec/overrides.md, "Decision kinds".
DECISION_KINDS = Registry(
    "decision-kinds",
    (
        DecisionKind("override", ("session", "exercise", "override"), "required"),
        DecisionKind("park_session", ("session",), "none"),
        DecisionKind("resume_session", ("session",), "none"),
        DecisionKind("leave_warning", ("flag", "params_hash"), "required"),
        DecisionKind("training_max", ("exercise", "load"), "none"),
        DecisionKind("safety_ceiling", ("exercise", "load"), "optional"),
        DecisionKind(
            "activity_cap",
            (
                "activity_kind",
                "weekly_distance",
                "weekly_minutes",
                "single_distance",
                "single_minutes",
            ),
            "optional",
        ),
        DecisionKind("decline_ceiling", ("block",), "required"),
        DecisionKind("defer_deep_review", (), "required"),
        DecisionKind("against_research", ("ref",), "none"),
        DecisionKind("retire", ("decision",), "none"),
    ),
)


@dataclass(frozen=True)
class ConstraintKind:
    name: str
    takes_value: bool

    def describe(self) -> Row:
        return {"name": self.name, "takes_value": self.takes_value}


CONSTRAINT_KINDS = Registry(
    "constraint-kinds",
    (
        ConstraintKind("rpe_cap", True),
        ConstraintKind("load_cap", True),
        ConstraintKind("no_added_load", False),
        ConstraintKind("avoid", False),
    ),
)
NIGGLE_STATUSES = terms(
    "niggle-statuses", "reported", "aggravated", "easing", "chronic", "resolved"
)
FOLLOW_UP_EVENTS = terms("follow-up-events", "deferred", "kept", "resolved", "dropped")
CHECK_IN_STATUSES = terms("check-in-statuses", "current", "superseded")
GOAL_KINDS = terms("goal-kinds", "hypertrophy", "strength")
GOAL_STATUSES = terms("goal-statuses", "current", "superseded")
MILESTONE_TARGET_KINDS = terms(
    "milestone-target-kinds", "e1rm", "load_x_reps", "bodyweight_multiple"
)
PHASE_UNTIL_KINDS = terms(
    "phase-until-kinds", "date", "bodyweight_at_or_below", "bodyweight_at_or_above", "coachs_call"
)
