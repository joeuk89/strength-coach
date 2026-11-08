"""The ledger Draft `coach record` reads and the check-in file `coach checkin record` reads. Which
record tables each may carry is the `record-kinds` registry's; each table's shape is its
parser's."""

from typing import cast

from coach.core.check_in_file import parse_check_in_file
from coach.core.draft_schema import ITEMS, DraftKind, Json, Recording
from coach.core.ledger_draft import parse_ledger_draft
from coach.core.registries.agent import RECORD_KINDS

RECORD_EXAMPLE = """[[weigh_in]]
date = 2026-11-02
kg = 81.2
"""

CHECK_IN_EXAMPLE = """date = 2026-11-01
tier = "light"
read = "A steady week; sleep was short midweek."
"""

DECISIONS = """[[decision]]
kind = "override"
session = "upper"
exercise = "bb_bench_press"
until = 2026-12-01
because = "pain"
text = "dumbbells until the shoulder settles"
evidence = ["niggle:n-0001"]

[decision.override]
kind = "swap_exercise"
to = "db_bench_press"
start_load = 30
load_mode = "per_hand_x2"

[[decision]]
kind = "override"
session = "upper"
exercise = "bb_row"
override = { kind = "pin_load", load = 70 }
until = 2026-12-01
because = "coach_judgement"
text = "hold the row"

[[decision]]
kind = "override"
session = "lower"
exercise = "bb_back_squat"
override = { kind = "hold" }
until = 2026-12-01
because = "stall"
text = "repeat the squat"

[[decision]]
kind = "override"
session = "lower"
exercise = "bb_deadlift"
override = { kind = "restate_sets", sets = [{ count = 3, reps = 5, rpe = 8 }] }
until = 2026-12-01
because = "fatigue"
text = "three sets of five"

[[decision]]
kind = "override"
session = "lower"
exercise = "leg_curl"
override = { kind = "drop_line" }
until = 2026-12-01
because = "pain"
text = "no leg curls for now"

[[decision]]
kind = "park_session"
session = "conditioning"
because = "schedule"
text = "parked until the evenings are free"

[[decision]]
kind = "resume_session"
session = "conditioning"
because = "schedule"
text = "back on"

[[decision]]
kind = "ladder_rung"
session = "core"
exercise = "dead_bug"
rung = 2
because = "progress"
text = "two clean holds; the athlete said yes"

[[decision]]
kind = "leave_warning"
flag = "offgrid_anchor_ignored@line:lower/bb_back_squat"
params_hash = "sha256:0f"
until = 2026-12-01
because = "coach_judgement"
text = "the off-grid anchor stands"

[[decision]]
kind = "training_max"
exercise = "bb_back_squat"
load = 140
because = "coach_judgement"
text = "a training max from the last rep-out"

[[decision]]
kind = "safety_ceiling"
exercise = "bb_deadlift"
load = 180
until = 2026-12-01
because = "pain"
text = "no heavier while the back settles"

[[decision]]
kind = "activity_cap"
activity_kind = "run"
weekly_distance = 20
single_minutes = 60
because = "fatigue"
text = "keep the running modest"

[[decision]]
kind = "decline_ceiling"
block = "b-2026-10-05"
until = 2026-11-08
because = "fatigue"
text = "the ceiling waits a week"

[[decision]]
kind = "defer_deep_review"
until = 2026-11-15
because = "schedule"
text = "the deep review waits for the trip to end"

[[decision]]
kind = "against_research"
ref = "rn:deloads.10"
because = "athlete_request"
text = "more volume than the research suggests, by choice"

[[decision]]
kind = "retire"
decision = "d-0007"
because = "coach_judgement"
text = "the cap no longer applies"
"""

NIGGLES = """[[niggle]]
site = "left knee"
date = 2026-11-02
opened = 2026-10-30
status = "reported"
text = "aches on deep squats"
key = "knee"

[[niggle.constraints]]
kind = "rpe_cap"
pattern = "squat"
value = 7

[[niggle.constraints]]
kind = "load_cap"
exercise = "bb_back_squat"
value = 100

[[niggle.constraints]]
kind = "no_added_load"
exercise = "split_squat"

[[niggle.constraints]]
kind = "avoid"
pattern = "lunge"

[niggle.rehab]
session = "knee-rehab"
title = "Knee rehab"
cadence = "daily"
tier = "optional"
location = "home"

[[niggle.rehab.line]]
exercise = "spanish_squat"
load_mode = "bodyweight"
rest_s = 60
cues = "slow down"
start_load = 0
superset = "a"

[[niggle.rehab.line.sets]]
count = 3
type = "working"
duration_s = 45
rpe = 6

[[niggle.rehab.line.sets]]
count = 2
reps = 10

[[niggle]]
niggle = "n-0001"
date = 2026-11-03
status = "easing"

[[note]]
date = 2026-11-02
text = "the knee felt better by the evening"
about = "niggle:@knee"
key = "evening"
"""

FOLLOW_UPS = """[[follow_up]]
raised = 2026-11-02
due = 2026-11-09
text = "ask about the knee"
about = "niggle:n-0001"
key = "ask"

[[follow_up]]
follow_up = "f-0001"
kind = "deferred"
date = 2026-11-02
due = 2026-11-16
text = "no news yet"

[[follow_up]]
follow_up = "f-0001"
kind = "kept"
date = 2026-11-03
due = 2026-11-16

[[follow_up]]
follow_up = "f-0002"
kind = "resolved"
date = 2026-11-03

[[follow_up]]
follow_up = "f-0003"
kind = "dropped"
date = 2026-11-03
"""

ANNOTATIONS = """[[annotation]]
kind = "discount"
target = "workout:w-0012"
because = "fatigue"
text = "slept four hours"

[[annotation]]
kind = "repair"
target = "workout:w-0012"
because = "coach_judgement"
params = { exercise = "bb_back_squat" }

[[annotation]]
kind = "load_mode"
target = "workout:w-0012"
because = "kit"

[[annotation]]
kind = "void"
target = "workout:w-0013"
because = "athlete_request"

[[annotation]]
kind = "trained_unlogged"
target = "planned_session:ps-0004"
because = "schedule"

[[annotation]]
kind = "cancelled"
target = "planned_session:ps-0005"
because = "schedule"

[[annotation]]
kind = "miss_tag"
target = "planned_session:ps-0006"
because = "fatigue"

[[annotation]]
kind = "match"
target = "workout:w-0014"
because = "coach_judgement"
params = { planned_session = "planned_session:ps-0007" }
key = "matched"

[[annotation]]
withdraws = "a-0003"
key = "undo"
"""

READINGS = """[[weigh_in]]
date = 2026-11-02
kg = 81.2
key = "monday"

[[weigh_in]]
withdraws = "wi-0004"

[[sleep_night]]
night = 2026-11-01
hours = 7.5
key = "sunday"

[[sleep_night]]
withdraws = "sn-0004"

[[activity]]
date = 2026-11-02
kind = "run"
minutes = 30
rpe = 6
quality = false
distance_km = 5.2
text = "easy loop"
key = "run"

[[status_span]]
kind = "travel"
from_date = 2026-11-10
to_date = 2026-11-14
text = "away for work"
key = "trip"

[[status_span]]
withdraws = "ss-0002"
"""

LOGS = """[[workout]]
date = 2026-11-02
title = "Upper at the hotel"
session_id = "upper"
minutes = 50
session_rpe = 7
notes = "a hotel gym"
key = "hotel"

[[workout.sets]]
exercise = "db_bench_press"
set_type = "working"
weight_kg = 30
reps = 10
rpe = 8
note = "per hand"

[[workout.sets]]
exercise = "row_erg"
duration_s = 600
distance_m = 2000

[[exercise]]
id = "spanish_squat"
name = "Spanish squat"
pattern = "squat"
muscles = { primary = ["quads"], secondary = [] }
load_mode = "bodyweight"
equipment_kind = "band"
hevy_template_id = "custom-spanish-squat"
hevy_title = "Spanish Squat"
hevy_exercise_type = "weight_reps"
hevy_equipment = "resistance_band"
hevy_muscle_group = "quadriceps"
key = "spanish"
"""

RECORD_COVERAGE = (DECISIONS, NIGGLES, FOLLOW_UPS, ANNOTATIONS, READINGS, LOGS)

OBSERVATIONS = """[[observation]]
text = "sleep under seven hours tracks the missed sets"
evidence = ["workout:w-0012", "check_in:ci-0003"]
key = "sleep"

[[observation]]
retire = "o-0002"
because = "no longer true since the new job"
"""

HEADER = """date = 2026-11-01
tier = "deep"
read = "A hard week."
readiness = "ok"
window_start = 2026-10-26
"""

CHECK_IN_COVERAGE = (
    HEADER
    + """
[phase]
kind = "deficit"
rate_pct_bw_per_week = -0.5
until = { kind = "date", value = 2026-12-20 }
because = "lean out"

"""
    + OBSERVATIONS,
    HEADER + 'phase = { close = true, because = "the cut is done" }\n',
    HEADER
    + 'phase = { kind = "maintenance", until = { kind = "coachs_call" }, because = "hold" }\n',
    HEADER
    + 'phase = { kind = "surplus", until = { kind = "bodyweight_at_or_above", value = 85 }, '
    + 'because = "a slow gain" }\n',
    *(HEADER + document for document in RECORD_COVERAGE),
)


def _with_record_tables(recording: Recording, *, check_in: bool) -> Json:
    schema = recording.schema()
    tables: Json = {
        kind.name: {"type": "array", "items": recording.schema((kind.name, ITEMS))}
        for kind in RECORD_KINDS.entries
        if check_in or not kind.check_in_only
    }
    return schema | {"properties": cast(Json, schema["properties"]) | tables}


RECORD = DraftKind(
    "ledger",
    lambda data: parse_ledger_draft(data, verb="record", file="draft"),
    RECORD_EXAMPLE,
    RECORD_COVERAGE,
    lambda recording: _with_record_tables(recording, check_in=False),
)

CHECK_IN = DraftKind(
    "check-in",
    lambda data: parse_check_in_file(data, file="draft"),
    CHECK_IN_EXAMPLE,
    CHECK_IN_COVERAGE,
    lambda recording: _with_record_tables(recording, check_in=True),
)
