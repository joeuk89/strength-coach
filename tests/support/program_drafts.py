# ruff: noqa: E501
"""Program Drafts for tests: the worked Draft of the program spec, and a small builder."""

import copy
from typing import Any

from coach.render.toml import dumps

# The worked version-1 Draft, copied from docs/spec/program.md ("Worked example").
WORKED_DRAFT = """\
name = "Week A / Week B around the PT Tuesday (six days)"
kind = "redesign"
because = "first program: carried over from the archived instance as version 1"
emphasis = "hypertrophy"
location = "home"

[schedule]
rotation = ["A", "B"]

[schedule.A]
mon = "a-mon-lower"
tue = "pt-tuesday"
wed = "a-wed-lower"
fri = "a-fri-push"
sat = "a-sat-pull"
sun = "a-sun-push"

[schedule.B]
mon = "b-mon-pull"
tue = "pt-tuesday"
wed = "b-wed-push"
fri = "b-fri-lower"
sat = "b-sat-push"
sun = "b-sun-pull"

# [dose] and [deload] left unsaid: adopt fills per_muscle = 10, lift targets of 8 for
# bb_bench_press and pull_up, hard_weeks_ceiling = 6, set_cut_pct = 40, load_cut_pct = 0,
# rpe_cap = 8, test_priority_lifts = true, and shows them in the diff.

[[session]]
id = "pt-tuesday"
title = "PT session (gym, Tuesday evening) — chest/back or legs/core, PT-controlled"
kind = "coach_led"
tier = "core"
location = "gym"
estimated_sets = { chest = 4, lats = 4, biceps = 3, quadriceps = 4, glutes = 3, abdominals = 3 }

[[session]]
id = "a-mon-lower"
title = "Week A · Mon — Lower: squat + quads + core"
kind = "lifting"
tier = "core"

  [[session.line]]
  exercise = "bb_back_squat"
  sets = [
    { count = 1, type = "warm_up", reps = 5 },
    { count = 1, type = "warm_up", reps = 3 },
    { count = 4, reps = [6, 8], rpe = 8 },
  ]
  rest_s = 180
  cues = "brace before you unrack · knees track over toes · same depth every rep"
  scheme = { name = "double_progression" }
  start_load = 120

  [[session.line]]
  exercise = "db_bulgarian_split_squat"
  sets = [{ count = 3, reps = [8, 10], rpe = 8 }]
  rest_s = 120
  cues = "front heel drives · torso tall · back knee travels down, not forward"
  scheme = { name = "double_progression" }
  start_load = 15                       # per hand

  [[session.line]]
  exercise = "db_lunge"
  sets = [{ count = 3, reps = [10, 12], rpe = 9 }]
  rest_s = 75
  cues = "torso vertical · drive through the front heel · controlled step, no falling forward"
  scheme = { name = "double_progression" }
  start_load = 15

  [[session.line]]
  exercise = "custom_single_leg_standing_calf_raise_dumbbell"
  sets = [{ count = 3, reps = [12, 15], rpe = 9 }]
  rest_s = 75
  cues = "work off a step so the heel drops into a deep stretch · ~1 s pause at the top · no bounce"
  scheme = { name = "double_progression" }
  start_load = 20

  [[session.line]]
  exercise = "ab_wheel"
  sets = [{ count = 3, reps = [8, 12], rpe = 9 }]
  rest_s = 0
  cues = "ribs down, hips tucked · roll only as far as the brace holds · never let the lower back sag"
  scheme = { name = "hold" }
  superset = "core"

  [[session.line]]
  exercise = "custom_hollow_hold"
  sets = [{ count = 3, duration_s = 30 }]
  rest_s = 75
  cues = "lower back pressed flat · shorten the lever (tuck the knees) if it arches"
  scheme = { name = "hold" }
  superset = "core"

[[session]]
id = "b-sat-push"
title = "Week B · Sat — Push: chest + bench + triceps"
kind = "lifting"
tier = "core"
minutes = 90

  [[session.line]]
  exercise = "bb_bench_press"
  sets = [
    { count = 1, type = "warm_up", reps = 8 },
    { count = 1, type = "warm_up", reps = 5 },
    { count = 4, reps = 5, rpe = 8 },
  ]
  rest_s = 180
  cues = "shoulder blades pinned back and down · feet planted · bar to the lower chest, elbows ~45°"
  scheme = { name = "linear" }           # registry defaults: misses_before_reset = 2, reset_factor = 0.9; inside the priority-lift band (goals.md), so no warning
  start_load = 120

  # ... db_incline_bench_press, custom_ring_push_up, db_lateral_raise, custom_dip_negatives,
  # db_overhead_triceps_extension, db_fly as in the old session

[[session]]
id = "a-sat-pull"
title = "Week A · Sat — Pull: pull-ups + rows + biceps"
kind = "lifting"
tier = "core"
minutes = 90

  [[session.line]]
  exercise = "custom_scapular_pull_ups"
  sets = [{ count = 2, type = "activation", reps = [6, 8], rpe = 5 }]   # was a warm-up with no working sets; carries no working group, so the pull-up below still counts as first
  rest_s = 60
  cues = "neutral grip · elbows stay locked · pull the shoulder blades down and back · 1–2 s pause"
  scheme = { name = "hold" }

  [[session.line]]
  exercise = "pull_up"
  sets = [{ count = 1, reps = 1, rpe = 10 }]                            # the strict single: a working set, under hold
  rest_s = 120
  cues = "neutral grip (parallel handles) — same grip every test · full dead hang start · collarbone to the bar · strict, no kip · one attempt, then move on"
  scheme = { name = "hold" }

  [[session.line]]
  exercise = "assisted_pull_up"
  sets = [{ count = 4, reps = 8, rpe = 8 }]                              # the ladder's reps, sets and RPE: params never repeat a group
  rest_s = 120
  cues = "neutral grip (parallel handles) · foot in the band · full dead hang each rep · same strict path as an unassisted rep"
  scheme = { name = "assistance_ladder", rungs = [60, 50, 40, 30, 20, 10, 0] }
  start_load = 60

  # ... custom_negative_pull_up, bb_bent_over_row, db_single_arm_row,
  # custom_straight_arm_lat_pulldown_band, db_incline_curl, db_hammer_curl,
  # custom_flexed_arm_hang, custom_dead_hang as in the old session

# cond-swings and cond-circuit: kind = "conditioning", tier = "optional", cadence = "standing",
# scheme = { name = "emom_density", minutes = 12, minutes_cap = 16, minutes_step = 2,
#            reps = { kb_swing = 12 }, reps_cap = { kb_swing = 15 }, rpe_target = 7 }
# and the circuit's equivalent; both were "parked" in the old file, which here is a park
# Decision recorded at migration, not a field.

[[acknowledge]]
flag = "scheme_off_emphasis@line:a-sat-pull/pull_up"
because = "coach_judgement"
text = "The pull-up progresses through the assistance ladder and negatives; the weekly single is the measure."
"""

WORKED_GOAL_PRIORITY_LIFTS = ("bb_bench_press", "pull_up")

# cutover.md's ten custom templates, plus the two the worked Draft names beyond them.
CUSTOM_EXERCISES: dict[str, dict[str, Any]] = {
    "custom_arch_hold": {"load_mode": "duration", "equipment_kind": "bodyweight"},
    "custom_decline_lateral_raise": {"load_mode": "per_hand_x2", "equipment_kind": "dumbbell"},
    "custom_dip_negatives": {"load_mode": "bodyweight", "equipment_kind": "bodyweight"},
    "custom_flexed_arm_hang": {"load_mode": "duration", "equipment_kind": "bodyweight"},
    "custom_hollow_hold": {
        "load_mode": "duration",
        "equipment_kind": "bodyweight",
        "muscles": {"primary": ["abdominals"], "secondary": []},
    },
    "custom_jumping_pull_up": {"load_mode": "bodyweight", "equipment_kind": "bodyweight"},
    "custom_pallof_press_band": {"load_mode": "band", "equipment_kind": "band"},
    "custom_pull_up_top_hold": {"load_mode": "duration", "equipment_kind": "bodyweight"},
    "custom_straight_arm_lat_pulldown_band": {"load_mode": "band", "equipment_kind": "band"},
    "custom_suitcase_carry": {"load_mode": "single_implement", "equipment_kind": "dumbbell"},
    "custom_single_leg_standing_calf_raise_dumbbell": {
        "load_mode": "single_implement",
        "equipment_kind": "dumbbell",
        "muscles": {"primary": ["calves"], "secondary": []},
    },
    "custom_scapular_pull_ups": {"load_mode": "bodyweight", "equipment_kind": "bodyweight"},
}


def a_line(exercise: str = "bb_bench_press", **fields: Any) -> dict[str, Any]:
    line: dict[str, Any] = {
        "exercise": exercise,
        "sets": [{"count": 3, "reps": [6, 8], "rpe": 8}],
        "rest_s": 120,
        "scheme": {"name": "double_progression"},
        "start_load": 60,
    }
    line.update(fields)
    return {key: value for key, value in line.items() if value is not None}


def a_rung(exercise: str | None = None, **fields: Any) -> dict[str, Any]:
    rung: dict[str, Any] = {
        "exercise": exercise,
        "cues": f"{exercise or 'first'} cues",
        "sets": [{"count": 2, "duration_s": 30, "rpe": 6}],
    }
    rung.update(fields)
    return {key: value for key, value in rung.items() if value is not None}


def a_ladder_line(exercise: str = "plank", *rungs: dict[str, Any], **scheme: Any) -> dict[str, Any]:
    """An `exercise_ladder` line: the rungs given, or the line's own exercise then side_plank."""
    ladder = list(rungs) or [a_rung(), a_rung("side_plank")]
    return {
        "exercise": exercise,
        "rest_s": 60,
        "scheme": {"name": "exercise_ladder", **scheme, "rungs": ladder},
    }


def a_session(id_: str = "push", *lines: dict[str, Any], **fields: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "id": id_,
        "title": id_.title(),
        "kind": "lifting",
        "tier": "core",
        "line": list(lines) or [a_line()],
    }
    session.update(fields)
    return {key: value for key, value in session.items() if value is not None}


def a_draft(*sessions: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """A one-week redesign at `home` scheduling each session on its own weekday."""
    sessions = sessions or (a_session(),)
    days = ("mon", "wed", "fri", "tue", "thu", "sat", "sun")
    draft: dict[str, Any] = {
        "name": "Test program",
        "kind": "redesign",
        "because": "first program",
        "emphasis": "hypertrophy",
        "location": "home",
        "schedule": {
            "rotation": ["A"],
            "A": {
                day: s["id"] for day, s in zip(days, sessions, strict=False) if "cadence" not in s
            },
        },
        "session": list(sessions),
    }
    draft.update(fields)
    return {key: value for key, value in copy.deepcopy(draft).items() if value is not None}


def toml(draft: dict[str, Any]) -> bytes:
    return dumps(draft).encode("utf-8")


# The sessions the worked Draft elides ("the remaining sessions follow the same pattern"),
# one line each from the exercises its comments name, so its schedule names no missing session
# and every muscle the version's dose is judged on has a hard set.
_ELIDED = {
    "a-wed-lower": ("bb_romanian_deadlift", "Week A · Wed — Lower", 100),
    "a-fri-push": ("db_incline_bench_press", "Week A · Fri — Push", 15),
    "a-sun-push": ("db_lateral_raise", "Week A · Sun — Push", 15),
    "b-mon-pull": ("bb_bent_over_row", "Week B · Mon — Pull", 100),
    "b-wed-push": ("db_overhead_triceps_extension", "Week B · Wed — Push", 20),
    "b-fri-lower": ("bb_back_squat", "Week B · Fri — Lower", 100),
    "b-sun-pull": ("db_hammer_curl", "Week B · Sun — Pull", 15),
}
WORKED_DRAFT_COMPLETE = WORKED_DRAFT + "".join(
    f"""
[[session]]
id = "{id_}"
title = "{title}"
kind = "lifting"
tier = "core"

  [[session.line]]
  exercise = "{exercise}"
  sets = [{{ count = 3, reps = [8, 12], rpe = 8 }}]
  rest_s = 120
  scheme = {{ name = "double_progression" }}
  start_load = {start_load}
"""
    for id_, (exercise, title, start_load) in _ELIDED.items()
)


BALANCE_STANCES_DRAFT = """\
name = "Daily balance practice"
kind = "redesign"
because = "a balance board joined the daily practice"
emphasis = "hypertrophy"
location = "home"

[schedule]
rotation = ["A"]

[[session]]
id = "daily-balance"
title = "Daily practice · Balance board"
kind = "practice"
tier = "optional"
cadence = "daily"

  [[session.line]]
  exercise = "custom_balance_board_stand"
  rest_s = 30

    [session.line.scheme]
    name = "exercise_ladder"
    advance = { exposures = 2 }

    [[session.line.scheme.rungs]]
    cues = "both feet, still, near a wall · soft knees · eyes on a point ahead"
    sets = [{ count = 2, duration_s = 30, rpe = 5 }]

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_tilt"
    cues = "slow tilts front to back, then side to side · rim off the floor"
    sets = [{ count = 2, duration_s = 60, rpe = 6 }]

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_eyes_closed"
    cues = "eyes closed for the hold · slow quarter squats with eyes open between holds"
    sets = [{ count = 2, duration_s = 45, rpe = 6 }]
    advance = { exposures = 3 }

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_one_foot"
    cues = "one foot centred, the other lifted · switch feet each set"
    sets = [{ count = 4, duration_s = 20, rpe = 7 }]

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_one_foot_eyes_closed"
    cues = "one foot, eyes closed, a wall within reach"
    sets = [{ count = 4, duration_s = 15, rpe = 7 }]

# with Hevy on, each also carries the four template columns (New exercises, above)
[exercise.custom_balance_board_stand]
name = "Balance board: two feet, still"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "balance"
muscles = { primary = [], secondary = [] }

[exercise.custom_balance_board_tilt]
name = "Balance board: two feet, tilting"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "balance"
muscles = { primary = [], secondary = [] }

[exercise.custom_balance_board_eyes_closed]
name = "Balance board: eyes closed and squats"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "balance"
muscles = { primary = [], secondary = [] }

[exercise.custom_balance_board_one_foot]
name = "Balance board: one foot"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "balance"
muscles = { primary = [], secondary = [] }

[exercise.custom_balance_board_one_foot_eyes_closed]
name = "Balance board: one foot, eyes closed"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "balance"
muscles = { primary = [], secondary = [] }
"""


# The two worked ladders of docs/spec/program.md ("Worked example: a balance-board ladder",
# "Worked example: a pull-up negatives ladder").
BALANCE_HOLDS_DRAFT = """\
name = "Daily balance practice"
kind = "redesign"
because = "a balance board joined the daily practice"
emphasis = "hypertrophy"
location = "home"

[schedule]
rotation = ["A"]

[[session]]
id = "daily-balance"
title = "Daily practice · Balance board"
kind = "practice"
tier = "optional"
cadence = "daily"

  [[session.line]]
  exercise = "custom_balance_board_hold"
  rest_s = 30

    [session.line.scheme]
    name = "exercise_ladder"
    advance = { exposures = 2 }

    [[session.line.scheme.rungs]]
    cues = "both feet, still, near a wall · soft knees · eyes on a point ahead"
    sets = [{ count = 2, duration_s = 30, rpe = 5 }]

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_hold"
    cues = "both feet, still, near a wall · soft knees · eyes on a point ahead"
    sets = [{ count = 2, duration_s = 40, rpe = 5 }]

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_hold"
    cues = "both feet, still, near a wall · soft knees · eyes on a point ahead"
    sets = [{ count = 2, duration_s = 50, rpe = 6 }]
    advance = { exposures = 3 }

    [[session.line.scheme.rungs]]
    exercise = "custom_balance_board_hold"
    cues = "both feet, still, near a wall · soft knees · eyes on a point ahead"
    sets = [{ count = 2, duration_s = 60, rpe = 6 }]

[exercise.custom_balance_board_hold]
name = "Balance board hold"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "balance"
muscles = { primary = [], secondary = [] }
hevy_title = "Balance Board Hold"
hevy_exercise_type = "duration"
hevy_equipment = "other"
hevy_muscle_group = "other"
"""

PULL_UP_NEGATIVES_DRAFT = """\
name = "Pull day around the negatives"
kind = "redesign"
because = "the strict pull-up is built on longer negatives"
emphasis = "hypertrophy"
location = "home"

[schedule]
rotation = ["A"]

[schedule.A]
sat = "pull"

[[session]]
id = "pull"
title = "Sat — Pull: pull-up negatives"
kind = "lifting"
tier = "core"
minutes = 45

  [[session.line]]
  exercise = "negative_pull_up"
  rest_s = 120

    [session.line.scheme]
    name = "exercise_ladder"

    [[session.line.scheme.rungs]]
    cues = "jump or step to the top · lower for 4 s · dead hang at the bottom"
    sets = [{ count = 3, reps = 5, rpe = 8 }]

    [[session.line.scheme.rungs]]
    exercise = "negative_pull_up"
    cues = "jump or step to the top · lower for 6 s · dead hang at the bottom"
    sets = [{ count = 3, reps = 5, rpe = 8 }]

    [[session.line.scheme.rungs]]
    exercise = "negative_pull_up"
    cues = "jump or step to the top · lower for 8 s · dead hang at the bottom"
    sets = [{ count = 3, reps = 5, rpe = 8 }]

    [[session.line.scheme.rungs]]
    exercise = "custom_weighted_negative_pull_up"
    cues = "dumbbell between the feet · lower for 8 s · dead hang at the bottom"
    sets = [{ count = 3, reps = 5, rpe = 8 }]
    start_load = 10

[exercise.custom_weighted_negative_pull_up]
name = "Weighted negative pull-up"
load_mode = "single_implement"
equipment_kind = "dumbbell"
pattern = "vertical_pull"
muscles = { primary = ["lats"], secondary = ["biceps", "upper_back"] }
hevy_title = "Weighted Negative Pull Up"
hevy_exercise_type = "weight_reps"
hevy_equipment = "dumbbell"
hevy_muscle_group = "lats"
"""
