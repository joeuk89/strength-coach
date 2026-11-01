# ruff: noqa: E501
"""Goal Drafts the tests adopt; WORKED is goals.md's worked Draft, copied by hand."""

WORKED = '''kind = "hypertrophy"
because = "first goal at onboarding"
priority_lifts = ["bb_bench_press", "pull_up"]
why = """
Strong and jacked: big arms, legs, glutes and thick abs at a body fat that is easy to live at.
The test is jeans and a t-shirt. Bench and the strict pull-up first; the 2×BW deadlift is a
gym lift for later.
"""

[[milestones]]
exercise = "bb_deadlift"
target = { kind = "bodyweight_multiple", value = 2.0 }

[[milestones]]
exercise = "bb_bench_press"
target = { kind = "bodyweight_multiple", value = 1.25 }

[[milestones]]
exercise = "pull_up"
target = { kind = "load_x_reps", load = 0, reps = 5 }

[phase]
open = { kind = "maintenance", rate_pct_bw_per_week = 0.0, until = { kind = "coachs_call" }, because = "recomp at maintenance since 11 Oct 2026" }
'''

WORKED_WHY = (
    "Strong and jacked: big arms, legs, glutes and thick abs at a body fat that is easy to live "
    "at.\nThe test is jeans and a t-shirt. Bench and the strict pull-up first; the 2×BW deadlift "
    "is a\ngym lift for later.\n"
)

STRENGTH = """kind = "strength"
because = "bench first"
priority_lifts = ["bb_bench_press"]
why = "a bigger bench"
"""


def with_phase(goal: str, phase: str) -> str:
    return f"{goal}\n[phase]\n{phase}\n"


def opening(kind: str = "surplus", because: str = "bulk") -> str:
    return (
        f'open = {{ kind = "{kind}", until = {{ kind = "coachs_call" }}, because = "{because}" }}'
    )
