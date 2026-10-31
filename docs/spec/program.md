# Program authoring: the form, adoption and its checks

Spec for wayfinder #22. The decision is ADR 0015 (one whole-version file, one Program per
instance, the version kind decides the block). Nouns are in `GLOSSARY.md`; the emphasis
defaults adopt fills come from `goals.md`; the flag codes raised here are rows in
`validation.md`.

The shape in one paragraph: the agent writes a TOML Draft holding the **whole** next Program
version, usually starting from `program show --draft`, and runs `program adopt <file>`. Adopt
validates it offline (no Hevy call, ADR 0011), fills every default the version's emphasis owns,
freezes the Acknowledgements the Draft carries, and records an immutable version row. The dry run
shows the diff against the previous version with the filled defaults in it. The version is then
the only thing `prescribe` reads (ADR 0003, 0014).

## The authored form

One TOML file. Every key below is the schema; an unknown key anywhere is a violation
(`unknown_key`), never ignored.

### Top level

| Key | Required | Notes |
| --- | --- | --- |
| `name` | yes | Prose, the version's title in rendered pages |
| `kind` | yes | `amend` or `redesign` (ADR 0015) |
| `because` | yes | Why this version supersedes the previous one; "first program" at onboarding. For a promoted swap it cites the override |
| `emphasis` | yes | `hypertrophy`, `strength` or `maintenance` (ADR 0014) |
| `location` | yes | The default location for every session; must be a `[location.<name>]` in `coach.toml` |
| `[schedule]` | yes | Rotation weeks, below |
| `[dose]` | no | Filled from emphasis and phase when absent, below |
| `[deload]` | no | Filled from emphasis when absent, below |
| `[[session]]` | yes, at least one | Below |
| `[exercise.<id>]` | no | New library entries declared with the version, below |
| `[[acknowledge]]` | no | Acknowledgements of adopt warnings, below |

### Schedule

One shape, no rule plugins. `rotation` is an ordered list of week names; each named table maps
weekdays to session ids. A one-week rotation is the old `fixed_weekdays`; a coach-led session
that anchors the week is just a coach-led session on its weekday in every rotation week.

```toml
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
```

A session that appears in the schedule has cadence `weekly`. Standing and daily sessions declare
their cadence on the session and never appear in the schedule.

### Session

| Key | Required | Notes |
| --- | --- | --- |
| `id` | yes | Stable across versions: the Routine map, park and resume Decisions, matching and the hard-week count hang off it. A renamed id is a retired session plus a new one |
| `title` | yes | |
| `kind` | yes | `lifting`, `conditioning`, `practice`, `coach_led`. Never `rehab`: a rehab session is carried by its niggle (ADR 0010) |
| `tier` | yes | `core` or `optional`. A practice must be `optional` |
| `cadence` | when not in the schedule | `standing` or `daily`; a scheduled session is `weekly` and may not state a cadence |
| `location` | no | Departs from the version's default |
| `minutes` | no | The session's time budget; the rest-and-sets estimate over it is a warning |
| `scheme` | conditioning only | Session-level scheme, below |
| `estimated_sets` | coach-led only | `{ chest = 4, lats = 4, ... }` hard sets per muscle; a coach-led session has no lines |
| `[[session.line]]` | lifting, conditioning, practice | Below |

No `status`: a parked session is a Decision, not a field (ADR 0010).

### Line

| Key | Required | Notes |
| --- | --- | --- |
| `exercise` | yes | A library id; once per session at most |
| `load_mode` | no | Only when it departs from the Exercise's default; the Load type does the conversion |
| `[[session.line.sets]]` | yes, at least one group | Set groups, below |
| `rest_s` | yes | Seconds after each set of the line |
| `cues` | no | Free text, the canonical form cues |
| `scheme` | yes | `{ name = "...", ...params }`; the registry below |
| `start_load` | load-bearing lines only | Athlete units; per hand for per-hand modes. See **Start loads** |
| `superset` | no | A label; lines sharing it in one session are performed together |

### Set group

| Key | Required | Notes |
| --- | --- | --- |
| `count` | yes | Sets in the group |
| `type` | no, default `working` | `warm_up`, `working`, `activation`, `test` |
| `reps` | reps-based | An integer, a range `[6, 8]`, or an open top `"8+"` for a rep-out |
| `duration_s` | duration lines | Instead of `reps` |
| `rpe` | no | Stored as RPE on every group; a hypertrophy line renders it as RIR (`10 − rpe`) |

Set types:

- `warm_up` groups carry `count` and `reps` only; their loads are derived from the working load
  by the ADR 0008 ladder and never authored.
- `working` is the default. Sets to failure are working sets; a rep-out is a working group with
  an open top.
- `activation` is a real type: low load, counts no hard set, excluded from e1RM and from the
  working-set count. A line whose only groups are activation is valid and yields no Exposure
  (the old "warm-up with no working sets" problem, review "The data model").
- `test` is a heavy single or an AMRAP that sets the next block's training max (a `training_max`
  Decision, ADR 0016), allowed only under a scheme whose registry row permits it.

Set structures (drop sets, rest-pause, myo-reps) are not in v1. The evidence puts them level with
straight sets for growth and ahead only on time (`rn:progression-methods`), no source uses one
as a stall response, and the four set types cannot express them: a group would need its own
rest, a load taken from the group before it, and a rule for which of its sets count as hard
sets and qualify for e1RM. A version that wants one authors plain working sets. When they
arrive, the opening set of a myo-rep cluster is a `working` set, so `activation` keeps its
meaning.

### Dose and deload

Both are version tables so that `prescribe` reads the version only. Absent, adopt fills them
from the emphasis and the open Phase (`goals.md`, "Defaults per emphasis") and the dry run shows
the filled values. Present, they stand and may draw `dose_off_band` or `deload_off_emphasis`.

```toml
[dose]
per_muscle = 10          # hard sets per muscle per week
[dose.lift]
bb_bench_press = 8       # one entry per priority lift
pull_up = 8

[deload]
hard_weeks_ceiling = 6   # the Block ceiling; was `blocks.hard_weeks_ceiling`
set_cut_pct = 40
test_priority_lifts = true
```

### New exercises

A line references an Exercise by library id. The engine ships its catalogue as seed data the
store imports at `init`; the instance's library is the store's `exercise` table and nothing
else. A new exercise is declared in the same Draft and upserted in adopt's transaction:

```toml
[exercise.custom_ring_push_up]
name = "Ring push-up"
load_mode = "bodyweight"
equipment_kind = "bodyweight"
pattern = "horizontal_push"
muscles = { primary = ["chest"], secondary = ["triceps", "front_delts"] }
# without a Hevy template id, the four template columns (ADR 0011):
hevy_title = "Ring Push Up"
hevy_exercise_type = "reps_only"
hevy_equipment = "other"
hevy_muscle_group = "chest"
```

A declared exercise that already exists is updated field by field; `hevy_template_id` is never
set here (it is written by `plan apply` after a verified create, ADR 0011).

### Acknowledgements

The same shape as the plan Draft's (`validation.md`, "Leaving a warning"). Adopt freezes them on
the version; an entry whose key adopt did not raise is a violation so a stale acknowledgement
cannot ride along.

```toml
[[acknowledge]]
flag = "scheme_off_emphasis@line:b-sat-push/bb_bench_press"
because = "coach_judgement"
text = "Keep the 4×5 linear bench for one more block; the top-and-back-off switch waits for the first test week."
```

## What the form never carries

No loads except `start_load` and a ladder's `rungs`; no dates; no rotation position; no Hevy ids;
no session `status`; no per-line thresholds; no `increment` (the step is the rack's, below). The
old `interference`, `missed_day_rules`, `priority` and `external_sessions` blocks are gone:
priority lifts live on the Goal, interference is warnings in code, a missed day is a WeekPlan
override, and a coach-led session is a session kind.

## Schemes

One registry in code. Each scheme declares its name, a typed params table with defaults, the set
types it may drive, what it reads from history, its stall and reset rule (`prescription.md`)
and its deload shape. The form names a scheme and params only; `coach schema`
prints the registry so the agent never guesses a param. Scheme params are only what the rack
cannot know: the load step is the next row on the session location's rack at a plate-pool
location and the grid increment at a grid location (ADR 0008 precedence: location, exercise,
catalogue).

### Line schemes, v1

| Name | Params | Set types | Reads | Opening position with no history |
| --- | --- | --- | --- | --- |
| `double_progression` | none | warm_up, working, activation | reps at target RPE on the line's exposures | `start_load` at the bottom of the rep range |
| `linear` | `misses_before_reset`, `reset_factor` (registry defaults) | warm_up, working, activation | the last exposure's load and whether its sets were made | `start_load`, the authored sets |
| `hold` | none | warm_up, working, activation, test | nothing; the authored numbers stand until an override or a new version | the authored sets, `start_load` where load-bearing |
| `assistance_ladder` | `rungs` (assisted loads, descending), `reps`, `sets`, `rpe` | working | reps at RPE on the current rung | the first rung |
| `top_backoff` | `top = { reps, rpe }`, `backoff = { sets, reps, pct_of_top }` | warm_up, working, test | e1RM from the line's exposures, RPE as a cap | `start_load` is the top set; back-offs derive from it |
| `wave_531` | none; the registry holds the waves `[[65, 75, 85], [70, 80, 90], [75, 85, 95]]` of the training max at `5/3/1` reps, last working set open (`"5+"`, `"3+"`, `"1+"`) | warm_up, working, test | the current `training_max` Decision on the exercise and the last rep-out | `start_load` is the training max until a Decision exists |

`wave_531` is the slow strength cadence: the scheme the `program` skill names when `cadence_slow`
fires on a `top_backoff` lift (`goals.md`, **Response to a cadence signal**). Adopt never fills
it. Its wave is the Block's hard-week count, cycling; the light week is the version's deload
policy, not a fourth wave. It is the one v1 scheme that reads a `training_max`, so
`training_max_unused` fires on every other.

Not in v1, judged against the evidence (`rn:progression-methods`): `rpe_anchored` (it is
`top_backoff` under another name); `fixed_reps_rpe` (straight sets at an RPE-capped load are
`top_backoff` with `backoff = { sets = n − 1, reps = top.reps, pct_of_top = 100 }`);
`maintenance` (the emphasis cutting dose, not a scheme). Cluster sets change no outcome for this
athlete and are not a scheme.

### Session schemes, v1

Conditioning sessions carry their scheme at session level (ADR 0010) and derive this week's dose
from the last matched Activity; their lines use `hold`.

| Name | Params |
| --- | --- |
| `emom_density` | `minutes`, `minutes_cap`, `minutes_step`, `reps = { <exercise> = n }`, `reps_cap`, `rpe_target` |
| `circuit_rounds` | `rounds`, `rounds_cap`, `time_cap_minutes`, `reps = { <exercise> = n }`, `rpe_target` |

## Start loads

`start_load` is in athlete units and, for per-hand modes, per hand. The rules:

- A load-bearing line (`total`, `per_hand_x2`, `single_implement`, `assisted`, `band`) with no
  `start_load` and no Exposure of that exercise in the last 90 days is `start_load_missing`, a
  violation. With a recent Exposure the field is optional and history wins; when both exist and
  differ adopt warns `start_load_ignored`.
- A start load not on the session location's rack for the exercise's equipment kind is
  `start_load_off_rack`, a violation naming the two nearest rows. Adopt never rounds silently.
- Bodyweight and duration lines take no start load; one present is `unknown_key`.
- Before any Exposure, `prescribe` takes `start_load` as the load (already a rack row) and the
  scheme's opening position from the table above. Warm-up loads derive from it by the ADR 0008
  ladder.

## Adopt

`program adopt <draft> [--dry-run] [--position <week>]`. A plain store write, not an asked
verb (nothing leaves the store; `publish` commits the export as usual). It is one transaction:
validate, fill, upsert declared exercises, record the version, open or continue the Block.

- **Dry run** prints the diff against the previous version (sessions and lines added, removed,
  changed; the defaults the emphasis filled, marked as such), every flag, and each start load in
  athlete units with its Hevy kg. The `program` skill shows this to the athlete and runs the real
  adopt on their yes.
- **Kind.** `amend` continues the open Block and the rotation position. `redesign` closes the
  open Block, opens one dated today and restarts the rotation at the first week unless
  `--position` names another; a redesign with an open Block warns `block_open_at_redesign`.
- **Records**: the version row (sequence number, adopted date, `kind`, `because`, `emphasis`,
  the full form with filled defaults, the frozen Acknowledgements). The diff is derived from two
  version rows, never stored.
- **Never**: a Hevy call (template creation and routine writes belong to `plan apply`), a write
  to the Routine map, a rounding of any authored load, a rotation position for an `amend`.
- `program show --draft` emits the current version as a Draft; `--apply-plan <week>` folds that
  WeekPlan's swap and pin overrides in, so promoting a persisting swap is an `amend` the agent
  edits only to write `because`. The trigger for promotion is `overrides.md`'s: `override_persisting` on the third consecutive plan.

### Violations

| Code | Scope | Condition |
| --- | --- | --- |
| `unknown_key` | version | a key outside the schema, including `start_load` on a bodyweight or duration line |
| `unknown_exercise` | line | `exercise` is not in the library and not declared in the Draft |
| `unknown_scheme` | line or session | the scheme name or a param is not in the registry |
| `unknown_load_mode` | line | `load_mode` is not one of the glossary's |
| `duplicate_id` | version | two sessions share an id, or one exercise appears twice in a session |
| `schedule_session_missing` | version | the schedule names a session the version lacks |
| `session_unscheduled` | session | a session in no rotation week with no `cadence` |
| `cadence_on_scheduled` | session | a scheduled session states a cadence |
| `location_unknown` | version or session | a location with no `[location.<name>]` in `coach.toml` |
| `equipment_unsupplied` | line | the exercise's equipment kind is not mapped at the session's location (ADR 0008) |
| `rehab_in_version` | session | `kind = "rehab"` |
| `practice_not_optional` | session | a practice with `tier = "core"` |
| `coach_led_has_lines` | session | a coach-led session with lines, or a lifting session with `estimated_sets` |
| `start_load_missing` | line | above |
| `start_load_off_rack` | line | above |
| `no_working_sets` | line | zero working sets under a scheme that reads them (every scheme but `hold`) |
| `set_type_not_allowed` | line | a `test` group, or any type, under a scheme whose row does not permit it |
| `hevy_template_missing` | line | a new exercise without a template id lacks one of the four template columns (ADR 0011) |
| `acknowledgement_unmatched` | version | an `[[acknowledge]]` key adopt did not raise |
| `goal_missing` | version | no current Goal (`goals.md`) |
| `priority_lifts_required` | version | `strength` emphasis under a Goal with no priority lifts (`goals.md`) |

### Warnings (acknowledgeable, frozen on the version)

| Code | Scope | Params |
| --- | --- | --- |
| `emphasis_off_goal`, `scheme_off_emphasis`, `priority_lift_absent`, `priority_lift_not_first`, `dose_off_band`, `deload_off_emphasis` | as `goals.md` | as `goals.md` |
| `muscle_no_hard_sets` | version | muscle, sessions searched |
| `session_over_minutes` | session | estimate, `minutes` |
| `block_open_at_redesign` | version | block id, hard weeks so far |
| `start_load_ignored` | line | start load, last exposure load, exposure ref |
| `superset_rest_differs` | session | superset label, rest values |
| `session_retired` | version | session id, routine id if mapped |

## Worked example: the carried-over program as version 1

The old `program.json` (schema 10, "Week A / Week B around the PT Tuesday") translated by hand.
Exercise ids carry over unchanged. Shown in full for two sessions and the coach-led one; the
remaining sessions follow the same pattern. `kind = "redesign"` because it is the first version
and opens the first Block; `--position` carries the old rotation position across.

```toml
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
# bb_bench_press and pull_up, hard_weeks_ceiling = 6, set_cut_pct = 40,
# test_priority_lifts = true, and shows them in the diff.

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
  scheme = { name = "linear" }           # registry defaults: misses_before_reset = 2, reset_factor = 0.9
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
  sets = [{ count = 2, type = "activation", reps = [6, 8], rpe = 5 }]   # was a warm-up with no working sets
  rest_s = 60
  cues = "neutral grip · elbows stay locked · pull the shoulder blades down and back · 1–2 s pause"
  scheme = { name = "hold" }

  [[session.line]]
  exercise = "pull_up"
  sets = [{ count = 1, type = "test", reps = 1, rpe = 10 }]            # the strict single, under hold
  rest_s = 120
  cues = "neutral grip (parallel handles) — same grip every test · full dead hang start · collarbone to the bar · strict, no kip · one attempt, then move on"
  scheme = { name = "hold" }

  [[session.line]]
  exercise = "assisted_pull_up"
  sets = [{ count = 4, reps = [5, 6], rpe = 8 }]
  rest_s = 120
  cues = "neutral grip (parallel handles) · foot in the band · full dead hang each rep · same strict path as an unassisted rep"
  scheme = { name = "assistance_ladder", rungs = [60, 50, 40, 30, 20, 10, 0], reps = 8, sets = 4, rpe = 8 }
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
flag = "scheme_off_emphasis@line:b-sat-push/bb_bench_press"
because = "coach_judgement"
text = "Keep the 4×5 linear bench for one more block; top-and-back-off waits for the first test week."

[[acknowledge]]
flag = "scheme_off_emphasis@line:a-sat-pull/pull_up"
because = "coach_judgement"
text = "The pull-up progresses through the assistance ladder and negatives; the single is the test."
```

What the dry run shows for this file: the filled `[dose]` and `[deload]`; two `scheme_off_emphasis`
warnings, both acknowledged; `priority_lift_not_first` on `a-sat-pull` (the pull-up sits after
the scapular activation), left unacknowledged so it still shows; every `start_load` checked
against the home plate-pool snapshot; no violations. The old `increment` params are gone: the
squat steps by the home rack's next barbell row.

## Handed to other tickets

- **Weekly prescription** (#26, settled in `prescription.md`): the stall and reset rule per
  scheme, the registry defaults for `linear` (2, 0.9), the one-row step cap on `top_backoff`,
  `training_max_due` in place of a rule moving the training max, no coded RIR walk or set ramp,
  the derivation of a conditioning session's dose from its last Activity.
- **Override catalogue** (#19, settled in `overrides.md`): the trigger for promoting a one-week swap, the swap and pin
  override kinds `--apply-plan` folds in.
- **Verb set** (#16): `program adopt`, `program show` (`--draft`, `--apply-plan`), `coach schema`
  printing the scheme registry.
- **Schema**: the `program_version` table with sequence number, kind, because, emphasis, the
  form and the frozen Acknowledgements; the `exercise` table as the library seeded from the
  engine catalogue; the scheme registry as the source of `unknown_scheme`.
- **Migration**: the converter from the old `program.json` to this form, with the park Decisions
  for the two conditioning sessions and the old rotation position as `--position`.
