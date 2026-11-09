# Program authoring: the form, adoption and its checks

Spec for wayfinder #22. The decision is ADR 0015 (one whole-version file, one Program per
instance, the version kind decides the block). Nouns are in `GLOSSARY.md`; the emphasis
defaults adopt fills and the bands it warns against come from `goals.md`; the flag codes raised
here are rows in `validation.md`.

The shape in one paragraph: the agent writes a TOML Draft holding the **whole** next Program
version, usually starting from `program show --draft`, and runs `program adopt <file>`. Adopt
validates it offline (no Hevy call, ADR 0011), fills the three defaults the version's emphasis
owns (`[dose]`, `[deload]` and a lifting session's `minutes`; every line's scheme, RPE and rest
is authored, ADR 0014 amended), freezes the Acknowledgements the Draft carries, and records an
immutable version row. The dry run shows the diff against the previous version with the filled
defaults in it. The version is then the program's part of the prescribe request
(`prescription.md`, **What prescribe is handed**); `prescribe` never reads the Goal or the Phase
(ADR 0003, 0014).

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
weekdays to a session id or a non-empty list of session ids. A one-week rotation is the old
`fixed_weekdays`; a coach-led session that anchors the week is just a coach-led session on its
weekday in every rotation week.

Each entry is a slot, so a weekday may hold several sessions, of any kinds. List order is the
order within the day: the plan plans them in that order and every listing of the week shows them
in it. A one-element list and a bare id are the same schedule. A session scheduled beside another
keeps all its own fields (scheme, `minutes`, routine); nothing merges, and there is no day-level
time budget.

```toml
[schedule]
rotation = ["A", "B"]

[schedule.A]
mon = ["lower-a", "cond-swings"]
tue = "coach-led"
thu = "push-a"
sat = "pull-a"

[schedule.B]
mon = "pull-b"
tue = "coach-led"
thu = "lower-b"
sat = "push-b"
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
| `minutes` | no | The session's time budget; the rest-and-sets estimate over it is a warning. A lifting session that states none takes `[athlete].session_minutes`, filled into the version at adopt like an emphasis default |
| `scheme` | conditioning only | Session-level scheme, below |
| `estimated_sets` | coach-led only | `{ chest = 4, lats = 4, ... }` hard sets per muscle; a coach-led session has no lines |
| `[[session.line]]` | lifting, conditioning, practice | Below |

No `status`: a parked session is a Decision, not a field (ADR 0010).

### Line

| Key | Required | Notes |
| --- | --- | --- |
| `exercise` | yes | A library id; once per session at most, each distinct rung exercise of an `exercise_ladder` counting once. Under a ladder it is the first rung's exercise and the line's key for every scope (overrides, flags, one exercise per session); no rung re-keys the line |
| `load_mode` | no | Only when it departs from the Exercise's default; the Load type does the conversion |
| `[[session.line.sets]]` | yes, at least one group; none under `exercise_ladder`, whose rungs carry them (a line `sets` there is `unknown_key`) | Set groups, below |
| `rest_s` | yes | Seconds after each set of the line; the `program` skill proposes it from `goals.md`'s band, adopt never fills it |
| `cues` | no | Prose, the canonical form cues |
| `scheme` | yes | `{ name = "...", ...params }`; the registry below. Authored by the `program` skill, never filled: adopt warns `scheme_off_emphasis` when it sits outside the emphasis band (`goals.md`) |
| `start_load` | load-bearing lines only | Athlete units; per hand for per-hand modes. See **Start loads** |
| `superset` | no | A label; lines sharing it in one session are performed together |

### Set group

| Key | Required | Notes |
| --- | --- | --- |
| `count` | yes | Sets in the group |
| `type` | no, default `working` | `warm_up`, `working`, `activation`, `test` |
| `reps` | reps-based | An integer, a range `[6, 8]`, or an open top `"8+"` for a rep-out |
| `duration_s` | duration lines | Instead of `reps` |
| `rpe` | per the registry | Required on every working group of a scheme whose rule reads it (`double_progression`, `linear`, `assistance_ladder`, each rung of an `exercise_ladder`) and on the top group of `top_backoff`; missing is `rpe_missing`. Optional elsewhere (a back-off, a `hold` line, `wave_531`), where it is rendered and never a ceiling. Stored as RPE; a hypertrophy line renders it as RIR (`10 − rpe`). Never filled: the `program` skill proposes it from `goals.md`'s band |

Set types:

- `warm_up` groups carry `count` and `reps` only; their loads are derived from the first working
  set's load by the registry ramp and the ADR 0008 ladder (`prescription.md`, Warm-ups) and never
  authored.
- `working` is the default. Sets to failure are working sets; a rep-out is a working group with
  an open top.
- `activation` is a real type: low load, counts no hard set, excluded from e1RM and from the
  working-set count. A line whose only groups are activation is valid and yields no Exposure
  (the old "warm-up with no working sets" problem, review "The data model").
- `test` is the heavy single the deload policy prescribes on a priority lift in the light week,
  whose result the coach may record as the next block's training max (a `training_max` Decision,
  ADR 0016). It is never authored: a `test` group in the Draft is `set_type_not_allowed`. A
  weekly max attempt is a `working` single.

Set structures (drop sets, rest-pause, myo-reps) are not in v1. The evidence puts them level with
straight sets for growth and ahead only on time (`rn:progression-methods §1`), no source uses one
as a stall response, and the four set types cannot express them: a group would need its own
rest, a load taken from the group before it, and a rule for which of its sets count as hard
sets and qualify for e1RM. A version that wants one authors plain working sets. When they
arrive, the opening set of a myo-rep cluster is a `working` set, so `activation` keeps its
meaning.

### Dose and deload

Both are version tables so that `prescribe` reads the version, never the Goal or the Phase.
Absent, adopt fills them from the emphasis and the open Phase (`goals.md`, "Defaults per
emphasis") and the dry run shows the filled values. Present, they stand and may draw
`dose_off_band` or `deload_off_emphasis`. With a lifting session's `minutes`, these are the only
things adopt fills: a line's scheme, RPE and rest are coaching judgement the `program` skill
authors, and adopt warns where they sit outside the emphasis band.

```toml
[dose]
per_muscle = 10          # hard sets per muscle per week
[dose.lift]
bb_bench_press = 8       # one entry per priority lift
pull_up = { sets = 8, counts = ["negative_pull_up", "band_pull_up"] }

[deload]
hard_weeks_ceiling = 6   # the Block ceiling; was `blocks.hard_weeks_ceiling`
set_cut_pct = 40         # off each working group's sets in the light week
load_cut_pct = 0         # off the working load; the evidence keeps the load (rn:goal-programming §6)
rpe_cap = 8              # ceiling on every set in the light week
test_priority_lifts = true
```

The three shape fields are the light cut `prescription.md` applies on every lifting line of a
`light_week`; the override may restate any of them for one week (`overrides.md`).

A `[dose.lift]` entry is a bare target, or a table whose `sets` is the target and whose `counts`
names the lift's counted variants: exercises whose hard sets add to the lift's weekly figure,
one each, under the same exposure filter as the per-muscle dose (`week.md`, "Dose"). A lift
trained mostly through its rungs (a strict pull-up built with negatives and band pull-ups) keeps
a target inside the band this way. Adopt never fills `counts`; choosing a lift's variants is
coaching judgement. The variants count toward the target and the disrupted-week floor only:
they do not stand in for the lift on a line (`priority_lift_absent`), are never tested, and
need not come first in a session. `dose_off_band` reads `sets`, and adopt raises one for each
target outside its band, keyed on the target: `dose_off_band@dose:pv-2/per_muscle`,
`dose_off_band@dose:pv-2/bb_deadlift`.

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
# without a Hevy template id, the four template columns (ADR 0011); the last three take
# values from coach schema --registry hevy-exercise-types, hevy-equipment, hevy-muscle-groups:
hevy_title = "Ring Push Up"
hevy_exercise_type = "reps_only"
hevy_equipment = "other"
hevy_muscle_group = "chest"
```

A declared exercise that already exists is updated field by field; `hevy_template_id` is never
set here (it is written by `plan apply` after a verified create, ADR 0011).

`hevy_exercise_type`, `hevy_equipment` and `hevy_muscle_group` each name an entry of a registry
of the values Hevy accepts: `hevy-exercise-types`, `hevy-equipment` and `hevy-muscle-groups`,
listed by `coach schema --registry <name>`. Values match exactly, as Hevy matches them.
`hevy_title` is free text.

`pattern` names an entry of the `patterns` registry and every name in `muscles` an entry of the
`muscles` registry (ADR 0024); `coach schema --registry patterns` and `--registry muscles` list
them. A pattern row carries `heavy` and `compound`, a muscle row `dosed`, and the heavy-pattern,
compound and dosed lists the rules read are those flags. Empty `primary` and `secondary` lists
are legal. Adopt checks every exercise a line or a `counts` entry references and every one the
Draft declares, so a library row outside a registry fails at the next adopt that references it
and is fixed through the normal path.

### Acknowledgements

The same shape as the plan Draft's (`validation.md`, "Leaving a warning"). Adopt freezes them on
the version; an entry whose key adopt did not raise is a violation so a stale acknowledgement
cannot ride along. Adopt raises it once, naming every such entry in Draft order. An entry under
the old version-wide key of a warning now raised once per case (`dose_off_band@version:<id>`,
`priority_lift_absent@version:<id>`, `counted_variant_off_pattern@version:<id>`) is one: its
message says to remove it and lists the keys adopt raised for that code
(`dose_off_band@dose:...`, `priority_lift_absent@priority_lift:...`,
`counted_variant_off_pattern@counted_variant:...`).

```toml
[[acknowledge]]
flag = "scheme_off_emphasis@line:a-sat-pull/pull_up"
because = "coach_judgement"
text = "The pull-up progresses through the assistance ladder; the weekly strict single under hold is the measure, not the progression."
```

## What the form never carries

No loads except `start_load` and a ladder's `rungs`; no dates; no rotation position; no Hevy ids;
no session `status`; no per-line thresholds; no `increment` (the step is the rack's, below). The
old `interference`, `missed_day_rules`, `priority` and `external_sessions` blocks are gone:
priority lifts live on the Goal, interference is warnings in code, a missed day is a WeekPlan
override, and a coach-led session is a session kind.

## Schemes

One registry in code. Each scheme declares its name, a typed params table with defaults, the set
types it may drive, the shape its set groups must take and which of them carry `rpe`, what it
reads from history, and its stall and reset rule (`prescription.md`). No scheme declares a deload
shape: the light cut is one transform from the version's `[deload]` table, and the only
per-scheme behaviour under a cut is the return band's (`prescription.md`). The form names a
scheme and params only; `coach schema` prints the registry so the agent never guesses a param.
Scheme params are only what the set groups and the rack cannot say: a param never repeats a
group's `count`, `reps` or `rpe`, and the load step is the location's alone: the next row on
the session location's rack at a plate-pool location, the increment for the implement kind at a
grid location (ADR 0008). No exercise or catalogue entry carries an increment.

### Line schemes, v1

| Name | Params | Set types | Set groups (`set_groups_off_scheme` otherwise) | `rpe` required on | Reads | Opening position with no history |
| --- | --- | --- | --- | --- | --- | --- |
| `double_progression` | none | warm_up, working, activation | any | every working group | reps at the authored RPE on the line's anchor exposures | `start_load` at the bottom of the rep range |
| `linear` | `misses_before_reset`, `reset_factor` (registry defaults 2 and 0.9; `prescription.md`, Stalls, says why a coach names 0.95) | warm_up, working, activation | any | every working group | the anchor's load and whether its sets were made | `start_load`, the authored sets |
| `hold` | none | warm_up, working, activation | any | none | the anchor's top load, nothing else; the authored sets stand until an override or a new version | the authored sets, `start_load` where load-bearing |
| `assistance_ladder` | `rungs` (assisted loads, descending) | working | exactly one working group; its `count`, `reps` and `rpe` are the ladder's | the working group | reps at RPE on the current rung | the first rung |
| `exercise_ladder` | `rungs` (rung tables, below), `advance` (a criterion table, default `{ exposures = 2 }`) | working | on each rung, exactly one working group stating `reps` or `duration_s` | each rung's working group | reps or duration at RPE on the standing rung | the first rung |
| `top_backoff` | `pct_of_top` | warm_up, working | the first working group is the top (`count = 1`, an integer `reps`, `rpe`); at least one later working group, each a back-off at `pct_of_top` | the top group | the exercise-wide e1RM (`prescription.md`), the top group's RPE as a cap | `start_load` is the top set; back-offs derive from it |
| `wave_531` | none; the registry holds the waves `[[65, 75, 85], [70, 80, 90], [75, 85, 95]]` of the training max at `5/3/1` reps, last working set open (`"5+"`, `"3+"`, `"1+"`), the published numbers (rn:progression-training-age.9) | warm_up, working | one working group carrying `count` only; the wave owns reps and the open last set | none | the current `training_max` Decision on the exercise, the Block's hard-week count and the last rep-out | `start_load` is the training max until a Decision exists |

`exercise_ladder` is the ladder for work with no load to add, whose next step is a different exercise or a harder way of performing the same one (ADR 0023, ADR 0025): a bodyweight skill, a practice line. Lifting and practice sessions may carry one; a practice stays optional. The ladder is declared whole on the line; the line states no `sets`, and until a rung is chosen it stands on the first. Each `[[session.line.scheme.rungs]]` table:

| Key | Required | Notes |
| --- | --- | --- |
| `exercise` | yes, except on the first rung | A library id or one declared in the Draft's `[exercise.<id>]`; unknown is `rung_exercise_unknown`. The first rung is the line's `exercise` and may leave it unsaid. A rung may share its exercise with another rung when it differs in `sets` or `cues`; the rung's start (`prescription.md`) tells their histories apart (ADR 0025). A stance gets its own exercise only when the athlete wants it as its own history |
| `cues` | no | Prose, the rung's form cues. Tempo is written here: the engine cannot read it from a log or send it to Hevy, so a tempo rung's criterion is its reps at RPE and the athlete's yes to `rung_met` carries the word that the tempo was held (ADR 0025) |
| `sets` | yes | Exactly one working group with `reps` or `duration_s` and `rpe`; otherwise `set_groups_off_scheme` or `rpe_missing`. A hold-length climb is explicit rungs, one per duration (ADR 0025) |
| `advance` | no | The rung's criterion: restates or overrides the scheme-level `advance` key by key; `manual = true` stands alone |
| `start_load` | a load-bearing rung after the first; not on the first rung, whose start load is the line's | Athlete units; per hand for per-hand modes. See **Start loads** |

The criterion keys, at scheme level and on a rung: `reps` (a reps rung only), `duration_s` (a duration rung only), `rpe_at_most`, `exposures` and `manual` (`true`, with no other key: the athlete's word, for the rare rung the logs cannot tell). A key off its rung is `advance_criterion_off_rung`. With nothing said the criterion is every working set at the rung's reps or duration at or under its RPE on 2 consecutive exposures; a rep range reads its top and an open top `"8+"` its number. A ladder needs at least two rungs (`ladder_too_short`), and a rung equal to the one before it in `exercise`, `sets` and `cues` is `rung_repeated`; only neighbours are compared, so a ladder may return to an earlier shape later. The worked examples below show two in full.

Every surface names a rung by its label, `rung <n> · [<exercise name> · ]<dose>[ · <load>][ · <cues>]`, with the name only when the rung's exercise differs from the standing rung's (ADR 0025): `rung_met`'s message, the Hevy note's "Next:", the check-in card, the approval prompt, the routine page, the progress page and `program show`.

`wave_531` is the slow strength cadence: the scheme the `program` skill names when `cadence_slow`
fires on a `top_backoff` lift (`goals.md`, **Response to a cadence signal**). Adopt never fills
it. Its wave is the Block's hard-week count, cycling; the light week is the version's deload
policy, not a fourth wave. It is the one v1 scheme that reads a `training_max`, so
`training_max_unused` fires on every other.

Not in v1, judged against the evidence (`rn:progression-methods §2`): `rpe_anchored` (it is
`top_backoff` under another name); `fixed_reps_rpe` (straight sets at an RPE-capped load are
`top_backoff` with `backoff = { sets = n − 1, reps = top.reps, pct_of_top = 100 }`);
`maintenance` (the emphasis cutting dose, not a scheme). Cluster sets change no outcome straight
sets reach (`rn:progression-methods §2`) and are not a scheme.

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
  `start_load` and no Exposure of that exercise anywhere is `start_load_missing`, a violation:
  the same rule `prescribe` applies at anchor step 3, with no age limit (a stale anchor is the
  return band's business, `prescription.md`). With an Exposure the field is optional and history
  wins; when both exist and differ adopt warns `start_load_ignored`.
- A start load not on the session location's rack for the exercise's equipment kind is
  `start_load_off_rack`, a violation naming the two nearest rows. Adopt never rounds silently.
- Bodyweight and duration lines take no start load; one present is `unknown_key`.
- Before any Exposure, `prescribe` takes `start_load` as the load (already a rack row) and the
  scheme's opening position from the table above. Warm-up loads derive from it by the ADR 0008
  ladder.
- A rung of an `exercise_ladder` after the first carries its own `start_load`, and the rung's
  exercise decides whether it is load-bearing, in its own load mode (ADR 0025). A load-bearing
  rung with none is `start_load_missing` whatever its exercise's history, since exposures before
  a rung's start count for nothing on it, so history never waives it and it raises no
  `start_load_ignored`. A rung's load off the session location's rack is `start_load_off_rack`.
  Both are scoped to the line with the rung index in params. `start_load` on the first rung or on
  a rung that bears no load is `unknown_key`. The rung's load opens the line while it stands on
  the rung with no Exposure of the rung's exercise after the date of the rung's start, in the
  session or unmatched; after that the newest such Exposure's load holds, and the load never
  steps up. An Exposure on the Decision's own date belongs to the previous rung for this read,
  since neither carries a time of day and the workout that earned the climb is often logged that
  day; the criterion still counts it.

## Adopt

`program adopt <draft> [--dry-run] [--position <week>]`. A plain store write, not an asked
verb (nothing leaves the store; `publish` commits the export as usual). It is one transaction:
validate, fill, upsert declared exercises, record the version, open or continue the Block.

- **Dry run** prints the diff against the previous version (sessions and lines added, removed,
  changed; the defaults the emphasis filled, marked as such), every flag, each start load in
  athlete units with its Hevy kg (a ladder rung's with its index), and every session of the filled version, in version order,
  with its time estimate beside its filled `minutes`. The estimate sums `count × (duration_s +
  rest_s)` over each set group of the session's lines, with 40 s for a group that states no
  `duration_s`, and rounds up to whole minutes; it is null for a session with no lines or with
  no `minutes`, and it is the number `session_over_minutes` reports. The `program` skill shows
  this to the athlete and runs the real adopt on their yes.
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
| `unknown_key` | version | a key outside the schema, including `start_load` on a bodyweight or duration line or rung, or on a ladder's first rung |
| `unknown_exercise` | line | `exercise` is not in the library and not declared in the Draft |
| `unknown_scheme` | line or session | the scheme name or a param is not in the registry |
| `unknown_load_mode` | line | `load_mode` is not one of the glossary's |
| `unknown_pattern` | exercise | an exercise the Draft references or declares has a `pattern` outside the `patterns` registry |
| `unknown_muscle` | exercise or session | a name in an exercise's `primary` or `secondary` list, or a key of a coach-led session's `estimated_sets`, is outside the `muscles` registry |
| `duplicate_id` | version | two sessions share an id, one exercise appears twice in a session (a rung exercise of an `exercise_ladder` counts as one of its session's, once per line), or one session appears twice on a weekday |
| `schedule_session_missing` | version | the schedule names a session the version lacks |
| `session_unscheduled` | session | a session in no rotation week with no `cadence` |
| `cadence_on_scheduled` | session | a scheduled session states a cadence |
| `location_unknown` | version or session | a location with no `[location.<name>]` in `coach.toml` |
| `equipment_unsupplied` | line | a `total`, `per_hand_x2` or `single_implement` line whose equipment kind is not in the session location's `implements` (`instance.md`, ADR 0008) |
| `rehab_in_version` | session | `kind = "rehab"` |
| `practice_not_optional` | session | a practice with `tier = "core"` |
| `coach_led_has_lines` | session | a coach-led session with lines, or a lifting session with `estimated_sets` |
| `start_load_missing` | line | above |
| `start_load_off_rack` | line | above |
| `no_working_sets` | line | zero working sets under a scheme that reads them (every scheme but `hold`) |
| `set_type_not_allowed` | line | any authored `test` group (the deload policy alone prescribes one), or a type the scheme's row does not permit |
| `set_groups_off_scheme` | line | the working groups do not fit the scheme's row: a `top_backoff` first working group with `count` other than 1 or a range for `reps`, or no back-off group; more than one working group under `assistance_ladder`, or on a rung of an `exercise_ladder`; a rung group stating neither `reps` nor `duration_s`; a `wave_531` working group stating `reps` |
| `rpe_missing` | line | a working group the scheme's row requires `rpe` on has none, a rung's included |
| `rung_exercise_unknown` | version | a rung's `exercise` is not in the library and not declared in the Draft |
| `ladder_too_short` | line | an `exercise_ladder` with fewer than two rungs |
| `rung_repeated` | line | a rung equal to the one before it in `exercise`, `sets` and `cues` |
| `advance_criterion_off_rung` | line | `reps` on a duration rung, `duration_s` on a reps rung, or `manual` beside another key |
| `hevy_template_missing` | line | a new exercise without a template id lacks one of the four template columns (ADR 0011); only when `coach.toml` has a `[hevy]` table (`validation.md`) |
| `hevy_template_value_unknown` | line | under the same conditions, a template column present on the new exercise holds a value outside its registry (`hevy-exercise-types`, `hevy-equipment`, `hevy-muscle-groups`); one flag per bad column, none for an absent one |
| `acknowledgement_unmatched` | version | one or more `[[acknowledge]]` keys adopt did not raise, all named in one flag |
| `goal_missing` | version | no current Goal (`goals.md`) |
| `priority_lifts_required` | version | `strength` emphasis under a Goal with no priority lifts (`goals.md`) |
| `counted_variant_unknown` | version | a `counts` entry not in the library and not declared in the Draft |
| `counted_variant_not_exclusive` | version | an exercise in the `counts` of two lifts, or a priority lift in another lift's `counts` |

### Warnings (acknowledgeable, frozen on the version)

| Code | Scope | Params |
| --- | --- | --- |
| `emphasis_off_goal`, `scheme_off_emphasis`, `priority_lift_absent`, `priority_lift_not_first`, `dose_off_band`, `counted_variant_off_pattern`, `deload_off_emphasis` | as `goals.md` | as `goals.md` |
| `muscle_no_hard_sets` | version | muscle, sessions searched |
| `session_over_minutes` | session | estimate, `minutes` |
| `session_on_unavailable_day` | session | session id, weekday, `[athlete].available_days` |
| `block_open_at_redesign` | version | block id, hard weeks so far |
| `start_load_ignored` | line | start load, last exposure load, exposure ref |
| `superset_rest_differs` | session | superset label, rest values |
| `session_retired` | version | session id, routine id if mapped |

## Worked example: the old program restated as a version-1 Draft

The old `program.json` (schema 10, "Week A / Week B around the PT Tuesday") translated by hand,
to show the form on a real program. It is an illustration only: at cutover version 1 is designed
fresh with the old routines as reference (`cutover.md`). Shown in full for two sessions and the
coach-led one; the remaining sessions follow the same pattern. `kind = "redesign"` because it is
the first version and opens the first Block.

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
```

What the dry run shows for this file: the filled `[dose]` and `[deload]`; one `scheme_off_emphasis`
warning, on the pull-up's `hold` (a priority lift outside its band), acknowledged; none on the
bench, whose `linear` sits inside the priority-lift band; no `priority_lift_not_first` on `a-sat-pull` (the scapular line
ahead of the pull-up is activation only and carries no working group, so the pull-up is first);
every `start_load` checked against the home rack (`kit/home.achievable.json`, ADR 0021); no violations. The old `increment` params are gone: the
squat steps by the home rack's next barbell row.

## Worked example: a balance-board ladder

A daily practice line whose hold lengthens by 10 s once both holds are clean (issue #256,
ADR 0023, ADR 0025). All four rungs are one exercise, so its history stays whole, and the rung's
start tells them apart. A separate exercise is still right for a stance the athlete wants as its
own history. The first rung is the line's `exercise` and states none; the line states no `sets`,
since each rung carries its own. The ladder criterion is two exposures at the rung's duration at
or under its RPE; the third rung asks for three.

```toml
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
```

Adopt validates every rung and stores the ladder on the line; `program show` prints every rung
with its exercise, label, cues, sets and criterion. The template columns are needed only with
Hevy on (New exercises, above).

## Worked example: a pull-up negatives ladder

A tempo ladder on one exercise, topped by a weighted rung (ADR 0025). The first three rungs are
`negative_pull_up` at the same reps and differ only in their cues, which read lower for 4 s, 6 s
and 8 s. Each rung's criterion is its reps at RPE, and the athlete's yes to `rung_met` carries the
word that the tempo was held. The top rung is a load-bearing exercise, so it carries its own
`start_load`, on the home dumbbell rack in the athlete's units.

```toml
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
```

What the dry run shows for this file: no violations; `start_loads` lists the top rung, with its
index and Hevy-bound kg, and no other. The file is one session, so it also raises the warnings of a
week with nothing else in it (`priority_lift_absent`, `muscle_no_hard_sets`). Rung 4's label names its exercise while the line stands below it:
`rung 4 · Weighted negative pull-up · 3×5 @8 · 10 lb · dumbbell between the feet · lower for 8 s · dead hang at the bottom`.

## Handed to other tickets

- **Weekly prescription** (#26, settled in `prescription.md`): the prescribe request, the stall and reset rule per
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
- **Migration** (settled in `cutover.md`): no converter and no `--position`; version 1 is
  designed fresh by the `program` skill, and a park Decision for a conditioning session exists
  only if version 1 authors one.
