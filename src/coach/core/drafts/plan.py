from coach.core.draft_schema import DraftKind
from coach.core.plan_input import parse_plan_input

EXAMPLE = """week = 2026-11-02

[position]
week = "a"
confirmed = true
"""

COVERAGE = (
    """week = 2026-11-02
supersedes = "wp-0003"
note = ["the engine's notes are never read back"]
position = { week = "a", source = "rotation", confirmed = false }

[[override]]
kind = "light_week"
set_cut_pct = 30
load_cut_pct = 10
rpe_cap = 7
because = "fatigue"
text = "a lighter week after the trip"
evidence = ["check_in:ci-0004"]

[[override]]
kind = "minimum_week"
keep = ["upper", "lower"]
because = "schedule"
text = "two sessions this week"

[[override]]
kind = "one_off_week"
location = "hotel"
because = "schedule"
text = "away all week"

[[override]]
kind = "move_session"
session = "upper"
to = 2026-11-04
because = "schedule"
text = "moved to Wednesday"

[[override]]
kind = "drop_session"
session = "lower"
because = "schedule"
text = "no time"

[[override]]
kind = "add_session"
session = "extra"
date = 2026-11-06
location = "home"
because = "athlete_request"
text = "a short extra session"

[[override]]
kind = "relocate_session"
session = "upper"
location = "home"
because = "kit"
text = "the gym is shut"

[[override]]
kind = "swap_exercise"
session = "upper"
exercise = "bb_bench_press"
to = "db_bench_press"
start_load = 30
load_mode = "per_hand_x2"
because = "pain"
text = "the shoulder prefers dumbbells"

[[override]]
kind = "pin_load"
session = "upper"
exercise = "bb_row"
load = 70
because = "coach_judgement"
text = "hold the row at 70"

[[override]]
kind = "hold"
session = "lower"
exercise = "bb_back_squat"
because = "stall"
text = "repeat last week's squat"

[[override]]
kind = "restate_sets"
session = "lower"
exercise = "bb_deadlift"
sets = [{ count = 1, type = "warm_up", reps = 5 }, { count = 3, reps = [6, 8], rpe = 8 }]
because = "fatigue"
text = "fewer sets this week"

[[override]]
kind = "restate_sets"
session = "lower"
exercise = "plank"
sets = [{ count = 3, duration_s = 45 }]
because = "fatigue"
text = "shorter holds"

[[override]]
kind = "drop_line"
session = "lower"
exercise = "leg_curl"
because = "pain"
text = "the knee is sore"

[[acknowledge]]
flag = "offgrid_anchor_ignored@line:lower/bb_back_squat"
params_hash = "sha256:0f"
because = "coach_judgement"
text = "the off-grid anchor was a one-off"
evidence = ["workout:w-0012"]

[[session]]
id = "upper"

[[flag]]
code = "offgrid_anchor_ignored"
""",
)

PLAN = DraftKind("plan", lambda data: parse_plan_input(data, file="draft"), EXAMPLE, COVERAGE)
