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

Two flags with the same code on the same scope cannot exist: a code states one condition per
scope, so the key is a key. The message is display only and is never stored. The params (the
facts of the condition: a streak length, a ceiling and its kind, a drift class) ride alongside
the key and are hashed separately; they are condition facts only, never derived display numbers
that move with rounding.

The key renders as one string, `code@scope-ref`, with the ref's parts joined by `/`:

```
stall_streak@2026-11-03/upper-a/ohp
block_ceiling_exceeded@2026-11-03
routine_drift@abc123
engine_pin_dev@instance
```

That string is what the agent writes in a Draft to acknowledge a warning and what `--fields`
filters on. The params hash is a separate field, never part of the string.

## One Flag shape everywhere

Every violation and warning, in the envelope's `warnings[]` or in a plan result's `violations[]`
and `warnings[]`, is the same object:

```json
{
  "key": "stall_streak@2026-11-03/upper-a/ohp",
  "code": "stall_streak",
  "severity": "warning",
  "scope": {"kind": "line", "week": "2026-11-03", "session": "upper-a", "exercise": "ohp"},
  "params": {"streak": 3, "exposures": ["wk-7f2a/ohp", "wk-81c0/ohp", "wk-9d11/ohp"]},
  "params_hash": "sha256:…",
  "message": "OHP has stalled for 3 exposures at 42.5 kg",
  "left": null
}
```

`left` is `null` or `{because, text, source: "weekplan" | "decision", evidence: [...]}`. A
violation's `left` is always `null`: the shape has the field so one renderer serves both, and a
contract test holds that no verb declaration accepts a violation key as an acknowledgement.

## Leaving a warning

A warning is left by an **Acknowledgement**: `{key, params_hash, because, text, evidence}`. The
`because` categories are the override's (pain, kit, stall, fatigue, schedule, athlete request,
coach judgement); the text is the coach's voice, unpoliced; evidence refs are optional (niggle,
exposure, check-in). `plan validate` refuses an acknowledgement with no `because`.

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
- **No inheritance.** A superseding WeekPlan in the same span inherits nothing: `plan validate`
  reports a warning as left only if the Draft acknowledges it or a Decision covers it. Re-planning
  midweek restates the acknowledgements, which the agent does by starting the Draft from the
  current plan's export (a verb-set matter). No judgement is carried silently into a plan the
  coach did not look at.

### Longer than a week

An acknowledgement on a WeekPlan dies with that week: if the condition holds next week the
warning returns and the coach judges it again. When the coach wants it quiet for longer (the old
`repeated_decline` walk and the adherence suppression windows, which the parity checklist
replaced with a snooze date), the acknowledgement is a **Decision** of kind `leave warning`: the
same `{key, params_hash, because, text, evidence}` plus an until date. The validator treats the
warning as left while the Decision is in force and the params hash is unchanged.

A Decision names one full key, never a bare code: the coach cannot silence `session_volume_high`
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
| A tombstoned workout id reappearing (ADR 0011) | a `match` or `exclude` Annotation on the new version |
| A follow-up due | a Follow-up event (kept, deferred, resolved, dropped) |
| A niggle open with no load constraint | a Niggle constraint or close, through the niggle verb |
| Engine pin on a `.dev` build (ADR 0007) | pinning a release, or `coach upgrade` |
| Kit or Hevy snapshot older than its age limit (ADR 0008, ADR 0011) | `coach import` |

## Violations

No verb and no flag writes around a violation. `plan validate` reports every violation per
scope in one envelope and refuses approval while any stands anywhere in the plan. Each code in
the registry names the verb or record that clears it; a contract test holds that every
violation code has one (ADR 0005's consequence), so no constraint can exist that the agent cannot
lawfully change the fact behind.

## Code registry

The v1 codes, drawn from ADR 0005, 0008, 0010 and 0011. Later tickets add a code only by adding
a row here; a contract test holds that every code the engine emits is in this table.

### Violations

| Code | Scope | Params | Cleared by |
| --- | --- | --- | --- |
| `load_off_grid` | line | load, implement, location, nearest grid loads | a `pin load` override on a grid value; a kit change in `coach.toml`; `coach import` of a new plate-pool snapshot |
| `recovery_ceiling_exceeded` | line | ceiling kind (niggle, return band, illness, light week), ceiling, prescribed load or RPE, ref | the niggle verb (close, or relax the constraint); the return band's exposure or days off; removing the light-week override; a lower `pin load` |
| `return_band_disagrees` | line | days off, band, load, set delta, RPE cap | removing or correcting the conflicting override so the band, load, set delta and RPE cap derive together |
| `block_ceiling_exceeded` | week | hard-week count, ceiling, block id | a Decision declining the ceiling, a light week override, or a block reset Decision |
| `hevy_template_missing` | line | exercise id, missing columns | editing the Exercise so its four template columns are present |
| `load_mode_mismatch` | line | exercise load mode, line load mode | editing the Exercise or the line's `pin load` |
| `plan_not_current` | week | named WeekPlan id, current draft hash | re-running the dry run on the current Draft |
| `rotation_unconfirmed` | week | inferred position, source | the agent confirming the rotation position in the Draft |

### Warnings on a plan (acknowledgeable)

| Code | Scope | Params |
| --- | --- | --- |
| `top_set_above_e1rm` | line | e1RM, model, load, RPE target |
| `no_e1rm` | line | exercise id, scheme |
| `increment_over_step` | line | increment, scheme step, from exposure |
| `offgrid_anchor_ignored` | line | exposure ref, logged load, anchor used |
| `over_rep_cap` | exposure | reps, cap |
| `short_sleep_week` | week | short nights, threshold, window |
| `stall_streak` | line | streak length, exposure refs |
| `unexplained_drift` | line | last prescription, this prescription, delta |
| `session_drop_suggested` | session | reason (sleep debt, status day, quality stack), evidence refs |
| `frozen_load_off_snapshot` | session | line, load, snapshot date |

### Warnings outside a plan (clear by fact)

| Code | Scope | Params |
| --- | --- | --- |
| `routine_drift` | routine | class (structural, load), plan in force, diff summary |
| `workout_reappeared` | workout | tombstone noticed at, new version `updated_at` |
| `followup_due` | instance | follow-up id, due date |
| `niggle_unconstrained` | instance | niggle id, opened |
| `engine_pin_dev` | instance | pinned version, running version |
| `snapshot_stale` | instance | source (plate-pool, hevy), snapshot date, age limit |

### Codes pending other tickets

The parity checklist holds further warning conditions whose rule is not yet specified: volume
undershoot and session volume high, the priority lift floor unplaceable, double-progression
mismatch, infeasible RPE target, the "choose the load" state, cardio cap and spike, same-day lift
and quality activity. Each lands here as a row when the weekly prescription rule or the override
catalogue settles its condition and params.

## Contract tests

- Every code the engine emits is a row in this registry, at the registry's severity and scope.
- Every violation code names a clearing verb or record, and that verb exists in the verb set.
- No verb declaration accepts a violation key as an acknowledgement.
- Rewording a message changes no key and no params hash: a fixture plan validated under two
  renderers reports identical keys.
- An acknowledgement whose params hash no longer matches is reported as not left.
