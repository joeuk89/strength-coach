# Validation: flags, their keys and how a warning is left

A flag is a violation or a warning. Its identity is the condition it states, never the words that
describe it, so rewording a message or re-deriving a plan cannot move it. A violation is cleared
only by changing the fact behind it through a verb (ADR 0005). A warning is left by a typed,
reasoned Acknowledgement that lives on the WeekPlan, or on a Decision when the coach wants it to
outlast the week.

Decided on wayfinder ticket [Flag identity and lifecycle](https://github.com/joeuk89/strength-coach/issues/23),
2026-10-27. The hard and warning conditions are ADR 0005's; Hevy's are ADR 0011's; the drop
warnings are ADR 0010's; the kit snapshot warning is ADR 0008's.

## Severity

Two severities, fixed per code: `violation` and `warning`. There is no `info`: anything the old
system reported at that level is either a warning the coach should judge or a figure on a
rendered page, not a flag. There is no coaching mode and no run-mode downgrade (ADR 0004: no
feature toggles); the structural warnings the old mode softened are ordinary warnings, left with
a reason like any other. No code changes severity at runtime: where the old system emitted one
code at two severities (planned versus logged volume), the registry holds two codes or one.

## Identity

The key of a flag is `(code, scope)`. Nothing else enters it.

- **Code**: a registry name, `[a-z][a-z0-9_]*`, one condition per code.
- **Scope**: the typed target the condition is about. Scope kinds and their refs:

| Kind | Ref | Raised on |
| --- | --- | --- |
| `week` | Monday date | a WeekPlan as a whole |
| `session` | Monday date, session id | a planned session |
| `line` | Monday date, session id, exercise id | one line of a planned session |
| `exposure` | Hevy workout id, exercise id | a logged exposure a line derives from |
| `routine` | Hevy routine id | a Routine map row at import |
| `workout` | Hevy workout id | a workout version at import |
| `instance` | none | the instance itself (setup, pins, snapshots) |
| `version` | program version id | a program version at adopt (ADR 0014) |
| `exercise` | exercise id | one exercise across blocks, for cadence signals and milestones (ADR 0014) |

Two flags with the same code on the same scope cannot exist: a code states one condition per
scope, so the key is a key. The message is display only and is never stored. The params (the
facts of the condition: a streak length, a ceiling and its kind, a drift class) ride alongside
the key and are hashed separately; they are condition facts only, never derived display numbers
that move with rounding.

The key renders as one string, the one key grammar every document uses:
`code@<scope kind>:<ref parts joined by />`, the kind alone when the scope has no ref. A dated
scope (`week`, `session`, `line` on a WeekPlan) leads with the Monday; the calendar-free form
(the same scopes at `program adopt`, and on a Decision, below) drops it:

```
stall_streak@line:2026-11-03/upper-a/ohp
block_ceiling_exceeded@week:2026-11-03
scheme_off_emphasis@line:b-sat-push/bb_bench_press
routine_drift@routine:3f9d2c7e-1b44-4a0e-8d55-c6a1e2b7f904
engine_pin_dev@instance
```

That string is what the agent writes in a Draft to acknowledge a warning and what `--fields`
filters on. The params hash is a separate field, never part of the string. Refs inside params
and evidence use `schema.md`'s ref grammar, which is separate from this key.

## One Flag shape everywhere

Every violation and warning, in the envelope's `warnings[]` or in a plan result's `violations[]`
and `warnings[]`, is the same object:

```json
{
  "key": "stall_streak@line:2026-11-03/upper-a/ohp",
  "code": "stall_streak",
  "severity": "warning",
  "scope": {"kind": "line", "week": "2026-11-03", "session": "upper-a", "exercise": "ohp"},
  "params": {"streak": 3, "exposures": ["exposure:b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13/ohp", "exposure:0c4a9e61-2f7b-4d13-b8e0-5a3d7c2f1e88/ohp", "exposure:9a1f6d3b-7e25-4c60-a2d4-e8b5f0c3a716/ohp"]},
  "params_hash": "sha256:…",
  "rn": "rn:…",
  "message": "OHP has stalled for 3 exposures at 42.5 kg",
  "left": null
}
```

`rn` is the citation of the constant that raised the flag: `rn:<note>.<n>` (a claim of a claims
note) or `rn:<note> §<n>` (a section of a prose note), `research-notes.md`'s two forms, or
`null` when a code rests on none (a Hevy shape, a pin, a number this framework chose). It sits outside `params` and the hash, so a note
renumbered or a citation added moves no key. It is the ref an `against_research` Decision or a
coach's explanation quotes; a running agent reads no note (ADR 0020). Rendered pages link it to
the note at the pinned engine tag.

`left` is `null` or `{because, text, source: "weekplan" | "decision", evidence: [...]}`. A
violation's `left` is always `null`: the shape has the field so one renderer serves both, and a
contract test holds that no verb declaration accepts a violation key as an acknowledgement.

## Leaving a warning

A warning is left by an **Acknowledgement**: `{key, params_hash, because, text, evidence}`. The
`because` categories are the override's (pain, kit, stall, fatigue, schedule, athlete request,
coach judgement); the text is the coach's voice, unpoliced; evidence refs are optional (niggle,
exposure, check-in). `plan apply --dry-run` refuses an acknowledgement with no `because`.

- **Home.** The agent writes acknowledgements in the plan Draft next to the overrides. They freeze
  onto the WeekPlan at approval and show at the approval prompt as "left warnings" with their
  reasons, beside the overrides.
- **Not leaving it.** A warning the agent does not acknowledge stays in the envelope and at the
  approval prompt for the athlete to see. Approval still proceeds: warnings never block. "Must
  read but may leave" means the athlete always sees what the coach left and why, or that it was
  left unexplained.
- **Binding.** An acknowledgement matches a flag when the key matches and the params hash is
  unchanged. A stall streak growing from 2 to 3 changes the hash, so the warning returns fresh
  and must be judged again.
- **No inheritance.** A superseding WeekPlan in the same span inherits nothing: `plan apply --dry-run`
  reports a warning as left only if the Draft acknowledges it or a Decision covers it. Re-planning
  midweek restates the acknowledgements, which the agent does by starting the Draft from the
  current plan's export (`query flags` and `query lines`, `verbs.md`). No judgement is carried silently into a plan the
  coach did not look at.

### Longer than a week

An acknowledgement on a WeekPlan dies with that week: if the condition holds next week the
warning returns and the coach judges it again. When the coach wants it quiet for longer (the old
`repeated_decline` walk and the adherence suppression windows, which the parity checklist
replaced with a snooze date), the acknowledgement is a **Decision** of kind `leave_warning`: the
same `{key, params_hash, because, text, evidence}` plus an until date. The validator treats the
warning as left while the Decision is in force and the params hash is unchanged.

A Decision names one full key, never a bare code: the coach cannot silence `session_dose_high`
everywhere for a block. A pattern that holds across lines earns a program change or an override
Decision, not a blanket silence. Because a Decision outlives any one week, its key uses the
calendar-free form of the scope: `session` and `line` refs without the Monday date (`session id`,
`session id / exercise id`); `exposure`, `routine`, `workout` and `instance` refs are already
calendar-free; a `week` scope cannot be the target of a Decision. The validator matches a
Decision's key against the dated scopes that resolve to it.

### Never deleted

No acknowledgement is deleted. A WeekPlan's are superseded with the plan; a Decision's ends by
its until date or is retired with a reason. Both stay readable in the ledger.

## Warnings outside a plan

Warnings the validator does not raise on a plan have no acknowledgement path. Each is reported in
the envelope `warnings[]` of the verb that finds it, and on the next plan's warnings where it
bears on a line, and clears only when the fact behind it changes through its own verb:

| Warning | Clears by |
| --- | --- |
| Drift on a live routine (ADR 0011) | an override on the next WeekPlan, or the next push overwriting it |
| A tombstoned workout id reappearing (ADR 0011) | a `match` or `void` Annotation on the new version |
| A follow-up due | a Follow-up event (kept, deferred, resolved, dropped) |
| A niggle open with no load constraint | a Niggle constraint or close, through a `[[niggle]]` record (`verbs.md`) |
| Engine pin on a `.dev` build (ADR 0007) | pinning a release, or `coach upgrade` |
| Kit or Hevy snapshot older than its age limit (ADR 0008, ADR 0011) | `coach import` |
| A cadence signal (`cadence_slow`, `cadence_fast`) | the signal no longer holding, or a version giving the exercise another scheme |
| A Phase off its trend | the observed rate back inside the band, or the Phase closing |
| A Phase condition met | the Phase closing (`goal adopt`) |
| A training max no scheme reads | retiring the Decision, or a version giving the exercise a scheme that reads it |
| A quality-bout cap exceeded, a run spike | history; the week closing |

Which verb reports each is `week.md`'s table.

## Violations

No verb and no flag writes around a violation. `plan apply --dry-run` (the only plan check, `verbs.md`) reports every violation per
scope in one envelope and refuses approval while any stands anywhere in the plan. Each code in
the registry names the verb or record that clears it; a contract test holds that every
violation code has one (ADR 0005's consequence), so no constraint can exist that the agent cannot
lawfully change the fact behind.

## Code registry

The v1 codes, drawn from ADR 0005, 0008, 0010, 0011, 0014 and 0015 (`program.md`). Later tickets add a code only by adding
a row here; a contract test holds that every code the engine emits is in this table. The
tables carry the registry's `rn` column, the citation each flag's `rn` field is filled from
(ADR 0020); `coach schema --registry flags` prints it. Where a code rests on several constants
the column names the citation per case. `null` marks a code that rests on no research: a shape,
a pin, or a number this framework chose, which `research-notes.md` lists as opinion.

### Violations

| Code | Scope | Params | Cleared by | `rn` |
| --- | --- | --- | --- | --- |
| `load_off_grid` | line | load, implement, location, nearest grid loads | a `pin load` override on a grid value; a kit change in `coach.toml`; `coach import` of a new plate-pool snapshot | `null` |
| `recovery_ceiling_exceeded` | line | ceiling kind (niggle, return band, illness, light week), ceiling, prescribed load or RPE, ref | a `[[niggle]]` record (close, or an event with a smaller constraint set); days off moved by a `trained_unlogged` Annotation or a hand-entered Workout; removing the light-week override or raising its `rpe_cap`; a lower `pin load` | by ceiling kind: return band rn:detraining-return.3, illness rn:detraining-return.4, light week rn:deloads.10, niggle `null` |
| `return_band_disagrees` | line | days off, band, load, set delta, RPE cap | removing or correcting the conflicting override so the band, load, set delta and RPE cap derive together; no override waives the band | rn:detraining-return.3 |
| `block_ceiling_exceeded` | week | hard-week count, ceiling, block id | a `decline_ceiling` Decision, a `light_week` override, or a `redesign` version | rn:deloads.3 |
| `hevy_template_missing` | line | exercise id, missing columns | an Exercise with a `hevy_template_id`, or one with all four template columns so `plan apply` can create the template; an Exercise that has the id never needs the other three (`cutover.md`) | `null` |
| `load_mode_mismatch` | line | exercise load mode, line load mode | editing the Exercise or the line's `pin load` | `null` |
| `plan_not_current` | week | named WeekPlan id, current draft hash | re-running the dry run on the current Draft | `null` |
| `rotation_unconfirmed` | week | inferred position, source | the agent confirming the rotation position in the Draft | `null` |
| `goal_missing` | version | none | `goal adopt` | `null` |
| `priority_lifts_required` | version | emphasis | a Goal with priority lifts, or a different emphasis | `null` |
| `unknown_key` | version | key path | removing the key from the program Draft | `null` |
| `unknown_exercise` | line | exercise id | an `[exercise.<id>]` declaration in the Draft, or a library id | `null` |
| `unknown_scheme` | line, session | scheme name, param | a registry scheme and its params | `null` |
| `unknown_load_mode` | line | load mode | a glossary load mode | `null` |
| `duplicate_id` | version | session id or (session, exercise) | unique ids; merging the duplicate lines | `null` |
| `schedule_session_missing` | version | week, weekday, session id | a session with that id, or removing the slot | `null` |
| `session_unscheduled` | session | session id | a slot in a rotation week, or a `cadence` | `null` |
| `cadence_on_scheduled` | session | session id, cadence | removing the cadence | `null` |
| `location_unknown` | version, session | location | a `[location.<name>]` in `coach.toml` | `null` |
| `equipment_unsupplied` | line | equipment kind, location | mapping the kind at the location, or another location or exercise | `null` |
| `rehab_in_version` | session | session id | removing it; a rehab session is raised on a niggle | `null` |
| `practice_not_optional` | session | session id | `tier = "optional"` | `null` |
| `coach_led_has_lines` | session | session id | removing the lines or the `estimated_sets` | `null` |
| `start_load_missing` | line | exercise id | a `start_load` on the line, or on the `swap_exercise` override that put the exercise there; raised only with no Exposure of the exercise anywhere, the same rule at adopt and in `prescribe` | `null` |
| `start_load_off_rack` | line | start load, location, two nearest rows | a start load on a rack row | `null` |
| `no_working_sets` | line | scheme | a working group, or `hold` | `null` |
| `set_type_not_allowed` | line | set type, scheme | a permitted type (`test` is never authored: a max attempt is a `working` single) | `null` |
| `set_groups_off_scheme` | line | scheme, expected shape | working groups that fit the scheme's registry row (`program.md`) | `null` |
| `rpe_missing` | line | scheme, group index | an `rpe` on the working group the scheme's row requires it on | `null` |
| `acknowledgement_unmatched` | version | flag key | removing the stale `[[acknowledge]]` entry | `null` |
| `record_kind_not_allowed` | instance | record kind, verb | moving the table to the file that may carry it (`verbs.md`: an Observation only in a check-in file) | `null` |
| `override_conflict` | week, session, line | the two kinds | removing one of the two overrides (`overrides.md`) | `null` |
| `reading_duplicate` | instance | reading kind, date or night, source, the live row's id | withdrawing one of the two rows in the Draft (`schema.md`, `check-in.md` "Correcting") | `null` |

### Warnings on a plan (acknowledgeable)

| Code | Scope | Params | `rn` |
| --- | --- | --- | --- |
| `top_set_above_e1rm` | line | e1RM, model, load, RPE target | rn:autoregulation.6 |
| `no_e1rm` | line | exercise id, scheme | rn:autoregulation.5 |
| `increment_over_step` | line | increment, scheme step, from exposure | `null` |
| `offgrid_anchor_ignored` | line | exposure ref, logged load, anchor used | `null` |
| `over_rep_cap` | exposure | reps, cap | rn:autoregulation.5 |
| `short_sleep_week` | week | short nights, threshold, window | rn:sleep-dieting.1 |
| `stall_streak` | line | streak length, exposure refs | rn:progression-methods §4 |
| `rep_range_missed` | line | set index, reps, range, logged RPE, authored RPE | `null` |
| `training_max_due` | line | training max, decision id or `start_load`, the three rep-out counts | rn:progression-training-age.9 |
| `rpe_ceiling_unchecked` | line | cap, clipped load, anchor exposure ref | rn:autoregulation.6 |
| `unexplained_drift` | line | last prescription, this prescription, delta | `null` |
| `session_drop_suggested` | session | reason (`status_span`, `quality_stack`; `week.md` defines the stack), evidence refs | `quality_stack` rn:concurrent-training.4 and .5; `status_span` `null` |
| `dose_under_target` | week | muscle, target, the four weekly figures (`week.md`) | rn:volume-frequency.1 |
| `session_dose_high` | session | planned fractional sets, ceiling (`week.md`) | rn:volume-frequency.3 |
| `frozen_load_off_snapshot` | session | line, load, snapshot date | `null` |
| `override_persisting` | line | kind, weeks, plan ids | `null` |
| `light_week_shape_off_trigger` | week | proposed shape, the plan's shape, triggers | rn:deloads.5, .8 to .10 |
| `light_week_unprompted` | week | hard-week count, ceiling | rn:deloads.3 and .4 |
| `minimum_week_floor` | week | priority lift, kept sessions | rn:minimum-effective-dose.4 |

### Warnings on a program version at adopt (acknowledgeable, frozen on the version)

| Code | Scope | Params | `rn` |
| --- | --- | --- | --- |
| `emphasis_off_goal` | version | goal kind, emphasis | `null` |
| `scheme_off_emphasis` | line | line scheme, emphasis, expected band (`goals.md` names the band per emphasis) | rn:goal-programming §4 |
| `priority_lift_absent` | version | exercise id | `null` |
| `priority_lift_not_first` | session | exercise id, position among the lines carrying a working group | rn:goal-programming §7 |
| `dose_off_band` | version | muscle or lift, target, band, phase | rn:goal-programming §3 |
| `deload_off_emphasis` | version | deload policy, expected shape | rn:goal-programming §6 |
| `muscle_no_hard_sets` | version | muscle, sessions searched | rn:volume-frequency.1 |
| `session_over_minutes` | session | estimate, `minutes` | `null` |
| `session_on_unavailable_day` | session | session id, weekday, `[athlete].available_days` | `null` |
| `block_open_at_redesign` | version | block id, hard weeks so far | `null` |
| `start_load_ignored` | line | start load, last exposure load, exposure ref | `null` |
| `superset_rest_differs` | session | superset label, rest values | `null` |
| `session_retired` | version | session id, routine id if mapped | `null` |
| `scheme_change_off_signal` | line | previous scheme, new scheme, signal key or none, `may_schemes` (`goals.md`, **Response to a cadence signal**) | rn:progression-methods §4 |
| `core_session_added_low_adherence` | session | session id, adherence, weeks counted (`week.md`) | rn:deloads.7 |

### Warnings outside a plan (clear by fact)

| Code | Scope | Params | `rn` |
| --- | --- | --- | --- |
| `routine_drift` | routine | class (structural, load), plan in force, diff summary | `null` |
| `workout_reappeared` | workout | tombstone noticed at, new version `updated_at` | `null` |
| `followup_due` | instance | follow-up id, due date | `null` |
| `niggle_unconstrained` | instance | niggle id, opened | `null` |
| `engine_pin_dev` | instance | pinned version, running version | `null` |
| `snapshot_stale` | instance | source (plate-pool, hevy), snapshot date, age limit (plate-pool 90 days, Hevy 7 days; opinion, `research-notes.md`) | `null` |
| `cadence_slow` | exercise | scheme, the scheme's metric (resets, stall streak or e1RM slope), blocks, `may_schemes`, `may`, `never` (the per-scheme condition and the switching table's row, `goals.md`) | rn:training-level §2 |
| `cadence_fast` | exercise | scheme, the scheme's metric (exposures at top of range, or exposures the one-row cap bound), `may_schemes`, `may`, `never`; raised only on `double_progression` and `top_backoff` | rn:training-level §2 |
| `phase_condition_met` | instance | phase id, condition, value | `null` |
| `phase_trend_off` | instance | phase id, target rate, observed rate, window | rn:training-level §4 |
| `activity_cap_exceeded` | week | cap, observed, activity refs; history, so it has no acknowledgement path and clears when the week closes | rn:running-load.5 and .6 |
| `run_spike` | workout or activity | run distance, longest in the previous 30 days, ratio; history, clears when the week closes (`week.md`) | rn:running-load.1 and .4 |
| `training_max_unused` | exercise | scheme, decision id | `null` |
| `exercise_unmapped` | workout | Hevy template id, title; a view over logged sets whose template id no Exercise carries, so an `[[exercise]]` record mapping or declaring the Exercise clears it for every version at once (`cutover.md`) | `null` |

### Codes pending other tickets

Settled by [The closed week](https://github.com/joeuk89/strength-coach/issues/38): volume
undershoot is `dose_under_target`, session volume high is `session_dose_high`, the run spike is
`run_spike`, same-day lift and quality activity is `session_drop_suggested` with reason
`quality_stack`, and `milestone_reached` is no code but a `progress` figure. The "choose the
load" state is `start_load_missing` on a swapped line and the cardio cap is
`activity_cap_exceeded` (`overrides.md`). The priority lift floor unplaceable (`minimum_week_floor`),
double-progression mismatch (`rep_range_missed`) and infeasible RPE target
(`rpe_ceiling_unchecked`) already have their rows.

## Contract tests

- Every code the engine emits is a row in this registry, at the registry's severity and scope.
- Every violation code names a clearing verb or record, and that verb exists in the verb set.
- No verb declaration accepts a violation key as an acknowledgement.
- Rewording a message changes no key and no params hash: a fixture plan validated under two
  renderers reports identical keys.
- An acknowledgement whose params hash no longer matches is reported as not left.
- Every `rn` in the registry resolves to a current claim in a research note (the ref test of
  ADR 0004 covers the registry as well as code).
