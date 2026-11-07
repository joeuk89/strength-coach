"""The program Draft `coach program adopt` reads. A scheme's params are the `schemes` registry's,
so each scheme table is one `oneOf` branch per scheme of its level; the exercise ladder's rung
table and criterion are the shapes the parser reads them with."""

from collections.abc import Callable, Mapping
from typing import Literal, cast

from coach.core.draft_schema import ITEMS, DraftKind, Json, Path, Recording
from coach.core.program.parse import parse_program_draft
from coach.core.registries.schemes import SCHEMES, ParamType, Scheme

POSITIVE: Json = {"type": "number", "exclusiveMinimum": 0}
PER_EXERCISE: Json = {"type": "object", "additionalProperties": POSITIVE}
# What each param type admits (checks.py's `_PARAM_TYPES`); a ladder's shapes are recorded.
PARAM_SHAPES: Mapping[ParamType, Json] = {
    "integer": {"type": "integer", "minimum": 1},
    "fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
    "percent": {"type": "number", "exclusiveMinimum": 0, "maximum": 100},
    "number": POSITIVE,
    "loads": {"type": "array", "minItems": 1, "items": {"type": "number"}},
    "per_exercise": PER_EXERCISE,
    "number_or_per_exercise": {"anyOf": [POSITIVE, PER_EXERCISE]},
}
LINE_SCHEME: Path = ("session", ITEMS, "line", ITEMS, "scheme")
SESSION_SCHEME: Path = ("session", ITEMS, "scheme")

EXAMPLE = """name = "Upper and lower"
kind = "redesign"
because = "a simple start"
emphasis = "strength"
location = "home"

[schedule]
rotation = ["A"]

[schedule.A]
mon = "upper"

[[session]]
id = "upper"
title = "Upper"
kind = "lifting"
tier = "core"

[[session.line]]
exercise = "bb_bench_press"
sets = [{ count = 3, reps = [6, 8], rpe = 8 }]
rest_s = 180
scheme = { name = "double_progression" }
start_load = 60
"""

LIFTING = """name = "Week A / Week B"
kind = "amend"
because = "every line scheme in one version"
emphasis = "hypertrophy"
location = "home"

[schedule]
rotation = ["A", "B"]

[schedule.A]
mon = "lower"
tue = ["upper", "mobility"]
wed = "skills"
thu = "pt"
fri = "lower"
sat = "upper"
sun = "mobility"

[schedule.B]
mon = "upper"

[dose]
per_muscle = 12
lift = { bb_bench_press = 8, pull_up = { sets = 10, counts = ["working", "test"] } }

[deload]
hard_weeks_ceiling = 6
set_cut_pct = 40
load_cut_pct = 10
rpe_cap = 8
test_priority_lifts = true

[[session]]
id = "lower"
title = "Lower"
kind = "lifting"
tier = "core"
cadence = "weekly"
location = "gym"
minutes = 60

[[session.line]]
exercise = "bb_back_squat"
load_mode = "total"
sets = [{ count = 1, type = "warm_up", reps = 5 }, { count = 4, reps = 5, rpe = 8 }]
rest_s = 180
cues = "brace"
scheme = { name = "linear", misses_before_reset = 2, reset_factor = 0.9 }
start_load = 100
superset = "a"

[[session.line]]
exercise = "bb_deadlift"
sets = [{ count = 1, reps = 3, rpe = 8 }, { count = 2, reps = 5, rpe = 7 }]
rest_s = 180
scheme = { name = "top_backoff", pct_of_top = 85 }
start_load = 140

[[session.line]]
exercise = "bb_overhead_press"
sets = [{ count = 3 }]
rest_s = 150
scheme = { name = "wave_531" }
start_load = 50

[[session.line]]
exercise = "plank"
sets = [{ count = 3, type = "activation", duration_s = 45 }]
rest_s = 60
scheme = { name = "hold" }

[[session]]
id = "upper"
title = "Upper"
kind = "lifting"
tier = "optional"

[[session.line]]
exercise = "pull_up"
sets = [{ count = 3, reps = "5+", rpe = 9 }]
rest_s = 120
scheme = { name = "assistance_ladder", rungs = [40, 25, 10] }

[[session.line]]
exercise = "push_up"
rest_s = 90

[session.line.scheme]
name = "exercise_ladder"
advance = { reps = 12, rpe_at_most = 8, exposures = 2 }

[[session.line.scheme.rungs]]
cues = "hands on a bench"
sets = [{ count = 3, reps = [8, 12], rpe = 8 }]

[[session.line.scheme.rungs]]
exercise = "deficit_push_up"
sets = [{ count = 3, duration_s = 30, rpe = 8 }]
advance = { duration_s = 45, manual = true }

[[session]]
id = "pt"
title = "PT session"
kind = "coach_led"
tier = "core"
estimated_sets = { chest = 4, lats = 4 }
"""

SESSIONS = """name = "Conditioning and practice"
kind = "redesign"
because = "every session scheme in one version"
emphasis = "maintenance"
location = "home"

[schedule]
rotation = ["A"]

[schedule.A]
mon = "skills"

[[session]]
id = "emom"
title = "EMOM"
kind = "conditioning"
tier = "optional"
cadence = "standing"

[session.scheme]
name = "emom_density"
minutes = 12
minutes_cap = 20
minutes_step = 2
reps = { kb_swing = 10 }
reps_cap = 15
rpe_target = 7

[[session.line]]
exercise = "kb_swing"
sets = [{ count = 12, reps = 10 }]
rest_s = 0
scheme = { name = "hold" }

[[session]]
id = "rounds"
title = "Rounds"
kind = "conditioning"
tier = "optional"

[session.scheme]
name = "circuit_rounds"
rounds = 4
rounds_cap = 6
time_cap_minutes = 25
reps = { burpee = 10 }
rpe_target = 8

[[session.line]]
exercise = "burpee"
sets = [{ count = 4, reps = 10 }]
rest_s = 0
scheme = { name = "hold" }

[[session]]
id = "skills"
title = "Handstand practice"
kind = "practice"
tier = "optional"
cadence = "daily"

[[session.line]]
exercise = "wall_handstand"
sets = [{ count = 5, duration_s = 30 }]
rest_s = 60
scheme = { name = "hold" }

[exercise.wall_handstand]
name = "Wall handstand"
load_mode = "duration"
equipment_kind = "bodyweight"
pattern = "vertical_push"
muscles = { primary = ["shoulders"], secondary = ["triceps"] }
hevy_title = "Wall Handstand"
hevy_exercise_type = "duration"
hevy_equipment = "none"
hevy_muscle_group = "shoulders"

[[acknowledge]]
flag = "scheme_off_emphasis@line:skills/wall_handstand"
because = "coach_judgement"
text = "practice holds stay on hold"
params_hash = "sha256:0f"
"""


def _scheme_branch(scheme: Scheme, recorded: Json) -> Json:
    properties = cast(dict[str, Json], recorded["properties"])
    params: Json = {
        param.name: properties[param.name]
        if param.type in ("rungs", "criterion")
        else PARAM_SHAPES[param.type]
        for param in scheme.params
    }
    return {
        "type": "object",
        "properties": {"name": {"const": scheme.name}, **params},
        "required": ["name", *(p.name for p in scheme.params if p.required)],
        "additionalProperties": False,
    }


def _schemes(level: Literal["line", "session"]) -> Callable[[Json], Json]:
    def shape(recorded: Json) -> Json:
        return {
            "oneOf": [
                _scheme_branch(scheme, recorded)
                for scheme in SCHEMES.entries
                if scheme.level == level
            ]
        }

    return shape


def _shaped(recording: Recording) -> Json:
    return recording.schema(
        replace={LINE_SCHEME: _schemes("line"), SESSION_SCHEME: _schemes("session")}
    )


PROGRAM = DraftKind(
    "program",
    lambda data: parse_program_draft(data, file="draft"),
    EXAMPLE,
    (LIFTING, SESSIONS),
    _shaped,
)
