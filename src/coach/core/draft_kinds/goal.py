from coach.core.draft_schema import DraftKind
from coach.core.goal import parse_goal_draft

EXAMPLE = """kind = "strength"
because = "a bigger bench first"
priority_lifts = ["bb_bench_press"]
why = "A bigger bench, then the rest."
"""

COVERAGE = (
    """kind = "hypertrophy"
because = "first goal at onboarding"
priority_lifts = ["bb_bench_press", "pull_up"]
why = "Bigger arms and legs."

[[milestones]]
exercise = "bb_deadlift"
target = { kind = "bodyweight_multiple", value = 2.0 }

[[milestones]]
exercise = "pull_up"
target = { kind = "load_x_reps", load = 0, reps = 5 }

[[milestones]]
exercise = "bb_bench_press"
target = { kind = "e1rm", value = 120 }

[phase.open]
kind = "deficit"
rate_pct_bw_per_week = -0.5
until = { kind = "date", value = 2026-12-20 }
because = "lean out"

[phase.close]
because = "the gain is done"
""",
    """kind = "strength"
because = "a heavier squat"
priority_lifts = ["bb_back_squat"]
why = "Squat first."

[phase]
open = { kind = "maintenance", until = { kind = "coachs_call" }, because = "recomp" }
""",
    """kind = "strength"
because = "a heavier squat"
priority_lifts = ["bb_back_squat"]
why = "Squat first."

[phase.open]
kind = "deficit"
because = "a slow cut"
until = { kind = "bodyweight_at_or_below", value = 80 }
""",
)

GOAL = DraftKind("goal", lambda data: parse_goal_draft(data, file="draft"), EXAMPLE, COVERAGE)
