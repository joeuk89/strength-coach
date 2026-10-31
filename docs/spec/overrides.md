# Override catalogue: the typed departures a WeekPlan and a Decision may carry

Spec for wayfinder #19, decided 2026-10-31. The decision behind it is ADR 0016; the override
shape (scopes, the reason triple, a load only as a typed field) is ADR 0005's; one-span versus
longer is ADR 0003's. Flag codes raised here are rows in `validation.md`; the Draft files are
`verbs.md`'s.

The shape in one paragraph: a WeekPlan carries overrides that live for its span, one flat
`[[override]]` array in the plan Draft. A Decision carries what lasts longer: an override
Decision wrapping one line-scope kind with an until date, or an agreement (a ceiling, a cap, a
parked session, a training max). Every kind is typed; the engine derives the prescription from
the version, the exposures and these records, and nothing else. No kind lets the agent write a
load except `pin_load`, whose load is a typed field that still passes the grid and every
recovery ceiling.

## WeekPlan overrides

One span, nothing finer than a line (ADR 0005). At most one override of each kind per scope
on one plan.

| Scope | Kind | Params | Effect |
| --- | --- | --- | --- |
| week | `light_week` | `type = "deload" \| "light"` | the deload policy's cut (two-thirds of the sets; loads −10 % or held; RPE 6 or ≤ 8); ends the block |
| week | `minimum_week` | `keep = [session ids]`, at most two | every other planned session is dropped by derivation; pauses the hard count |
| week | `one_off_week` | `location` optional | a travel or kit-constrained week; every session relocates when `location` is given; pauses the hard count |
| session | `move_session` | `to` date inside the week | the planned session moves; a move outside the week is a `drop_session` |
| session | `drop_session` | none | the planned session leaves the plan; a core-tier drop is a miss, an optional one is not (ADR 0010) |
| session | `add_session` | `session` id, `date`, `location` optional | a planned session with no slot behind it: any session of the version (parked ones included, as a one-off resume), a standing or a rehab session; never a body the version lacks |
| session | `relocate_session` | `location` | the planned session's rack is this location's |
| line | `swap_exercise` | `to` exercise id, `start_load` optional, `load_mode` optional | the line runs the other exercise under its scheme; with no exposure of `to` and no `start_load` the line is `start_load_missing` |
| line | `pin_load` | `load` (athlete units, per hand where the mode is per hand) | the working load this week; grid and ceiling checks still apply; spent once the exposure exists |
| line | `hold` | none | last exposure's dose repeated, no scheme step |
| line | `restate_sets` | the line's whole set groups, `program.md`'s shape | the only way to change one set |
| line | `drop_line` | none | the line leaves the session this week |

Not kinds, and why:

- **`replace_session`**: a `drop_session` plus an `add_session`.
- **`add_line`**: a new line needs a scheme and a start load, so it is a `swap_exercise` or a
  new version.
- **`cap_rpe` or a per-line load cap**: a niggle constraint, on the Niggle record (below).
- **`adopt_drift`**: routine drift (ADR 0011) is adopted by writing the matching line override
  (`pin_load`, `restate_sets`, `swap_exercise`) with `evidence = ["routine:<id>"]`, or the next
  push overwrites it.
- **A rotation position**: the WeekPlan's confirmed field, not a departure.

Two in a day is allowed (`move_session` onto a day that already has one raises nothing). An
added lifting session counts toward the hard-week gate like any other.

### Draft shape

Scope is given by which refs are present: none for the week, `session`, or `session` plus
`exercise`. Kind params sit inline beside the reason fields. Acknowledgements keep their own
`[[acknowledge]]` array (`validation.md`).

```toml
[[override]]
kind = "light_week"
type = "deload"
because = "fatigue"
text = "Sixth hard week and the squat drifted two sessions running."

[[override]]
kind = "swap_exercise"
session = "a-mon-lower"
exercise = "bb_back_squat"
to = "db_goblet_squat"
start_load = 24
because = "pain"
text = "Knee niggle flares under the bar; the goblet keeps the pattern."
evidence = ["niggle:n-0004"]

[[override]]
kind = "pin_load"
session = "b-sat-push"
exercise = "bb_bench_press"
load = 100
because = "coach_judgement"
text = "Open the new block two steps under the model; the last exposure was a grinder."
evidence = ["exposure:wk-9d11/bb_bench_press"]
```

## Decision kinds

The `[[decision]]` record kind (`verbs.md`) accepts exactly these. Every row carries the reason
triple; `until` where the table says so. Ids are engine-assigned (`d-0001`) and returned in the
`record` envelope.

| Kind | Params | Until | Supersedes |
| --- | --- | --- | --- |
| `override` | `session`, `exercise`, `override = { kind, ...params }` with one line-scope kind from the table above | required, at most 8 weeks | the earlier `override` on the same (session, exercise, override kind) |
| `park_session` / `resume_session` | `session` | none (ADR 0010) | the earlier one on the same session |
| `leave_warning` | `flag` (full calendar-free key), `params_hash` | required (`validation.md`) | the earlier one on the same key |
| `training_max` | `exercise`, `load` | none | the earlier one on the same exercise |
| `safety_ceiling` | `exercise`, `load` | optional | the earlier one on the same exercise |
| `activity_cap` | `activity_kind` (`run`), `weekly_distance` or `weekly_minutes`, `single_distance` or `single_minutes` | optional | the earlier one on the same activity kind |
| `decline_ceiling` | `block` id | none; lapses at the next week close, when the ceiling proposes again | the earlier one on the same block |
| `defer_deep_review` | none | required: the date it is due | the latest wins |
| `against_research` | `ref` (`rn:…`) | none | nothing |
| `retire` | `decision` id | none | ends the named Decision early |

An override Decision applies itself to every WeekPlan in its span: `prescribe` reads it beside
the plan's own overrides, the dry run lists it as in force, and the agent never restates it.
Where the plan carries an override of the same kind on the same line, the plan wins for that
week and the Decision stays recorded.

The old `[caps]` table is `safety_ceiling` rows; the old `[cardio]` weekly and single run caps
are `activity_cap` rows. The quality-bout cap, the spike ratio and the sleep numbers are engine
constants with their citation (ADR 0013).

No outcome field. A Decision is written only when it is made and its kind is the outcome: a
proposal the athlete takes becomes an override on the plan, a proposal declined is
`decline_ceiling`, a proposal nobody acted on is nothing. A superseded row keeps
`superseded_by`; a retired one keeps the retire row's id. Nothing is deleted.

### Draft shape

```toml
[[decision]]
kind = "override"
session = "a-mon-lower"
exercise = "bb_overhead_press"
override = { kind = "hold" }
until = "2026-12-20"
because = "fatigue"
text = "Hold the press through the deficit; the step returns with the surplus."

[[decision]]
kind = "activity_cap"
activity_kind = "run"
weekly_distance = 17
single_distance = 6
because = "athlete_request"
text = "Agreed at the 24 Oct check-in while the hamstring settles."
evidence = ["niggle:n-0003", "checkin:2026-10-24"]

[[decision]]
kind = "retire"
decision = "d-0007"
because = "coach_judgement"
text = "The hamstring is resolved; the run cap goes with it."
```

## What is not an override

- **Light week versus Decision.** Taking a light week is the `light_week` override on that
  WeekPlan, approved with it. Declining the ceiling's proposal is `decline_ceiling`. There is no
  block reset Decision: the Block closes by derived week kind (light, return, under half
  trained) or by a `redesign` version (ADR 0015).
- **Niggle constraints.** A niggle's load constraint (a cap, no added load, avoid an exercise or
  pattern) lives on the Niggle record and binds while its status says so (ADR 0010). A limit
  the athlete wants to outlive the niggle is a `safety_ceiling` with that reason, and the niggle
  closes. An `avoid` constraint removes or swaps the line by derivation, so `drop_line` is for
  schedule, kit and time.
- **A safety ceiling** truncates the rack for its exercise: no derived load crosses it, and a
  `pin_load` above it is `load_off_grid` with the ceiling named in the params.
- **A training max** is read only by the schemes that declare it (`top_backoff`; `wave_531` if
  #28 admits it). One on an exercise whose scheme ignores it is `training_max_unused`. A scheme
  that reads one and finds none derives from e1RM.

## The reason triple

Every override and Decision carries `because`, `text` and `evidence`:

- `because`: one of `pain`, `kit`, `stall`, `fatigue`, `schedule`, `athlete_request`,
  `coach_judgement` (ADR 0005). Any category on any kind; the pairing is never checked.
- `text`: required, the coach's voice, unpoliced.
- `evidence`: optional typed refs: `niggle:<id>`, `exposure:<workout>/<exercise>`,
  `checkin:<date>`, `routine:<id>`, `decision:<id>`.

## Precedence and conflicts

- At most one override per kind per scope on one WeekPlan.
- At most one of `light_week`, `minimum_week`, `one_off_week` per WeekPlan. Where the week kind
  falls among a `no_training` status span, these overrides, a layoff and an illness is the
  Weekly prescription rule's (#26), as is the per-line order of scheme, override, return decay,
  light-week cut, constraints, ceilings and rounding.
- `drop_session` and `drop_line` beat every other override on their scope.
- `pin_load` obeys every recovery ceiling: it can lower a load, never lift one above the ceiling.
- The plan's override beats an override Decision of the same kind on the same line.
- Anything else is the violation `override_conflict`, params the two kinds.
- A superseding midweek plan inherits nothing: the agent restates overrides from
  `query lines --changed`, as it restates acknowledgements (`validation.md`).

## Promotion

A line override of kind `swap_exercise`, `restate_sets`, `hold` or `drop_line` on three
consecutive approved WeekPlans for the same (session, exercise) raises `override_persisting` on
the third plan's dry run (scope line; params: kind, weeks, plan ids). `pin_load` never counts:
once the exposure exists history wins and the pin is spent. Weeks covered by an override
Decision never count: the Decision is the acknowledgement.

The agent then does one of three things, and nothing happens on its own:

1. **Promote**: `program show --draft --apply-plan <week>` folds the plan's line overrides
   into a Draft, then `program adopt` as an `amend` whose `because` cites the override
   (`program.md`).
2. **Extend**: an `override` Decision with an until date, at most 8 weeks.
3. **Leave it**: an Acknowledgement, and the warning returns on the next plan.

### What `--apply-plan` folds

| Override | Folds to |
| --- | --- |
| `swap_exercise` | the line's `exercise`, `load_mode` when given, and the swap's `start_load` |
| `restate_sets` | the line's set groups |
| `drop_line` | the line removed |
| `pin_load` | the line's `start_load`, labelled as a folded pin in the diff |
| `hold` | `scheme = { name = "hold" }` |

Session and week kinds never fold: a dropped session is parked by Decision or removed by hand
in the Draft.

## Flags this catalogue adds

Rows in `validation.md`'s registry:

| Code | Severity | Scope | Params |
| --- | --- | --- | --- |
| `override_conflict` | violation | line, session, week | the two kinds |
| `override_persisting` | warning (plan) | line | kind, weeks, plan ids |
| `light_week_type_off_trigger` | warning (plan) | week | proposed type, chosen type, triggers |
| `light_week_unprompted` | warning (plan) | week | hard-week count, ceiling |
| `minimum_week_floor` | warning (plan) | week | priority lift, kept sessions |
| `activity_cap_exceeded` | warning (outside a plan, no acknowledgement; history) | week | cap, observed, activity refs |
| `training_max_unused` | warning (outside a plan) | exercise | scheme, decision id |

`start_load_missing` gains a clearer: a `start_load` on the `swap_exercise` override. The
"choose the load" state pending in `validation.md` is this: with history the scheme derives,
without it the only lawful input is that typed field, so no other code exists for it.

## Handed to other tickets

- **Weekly prescription** (#26): the week-kind precedence, the per-line order of modifiers,
  what `hold` and the light-week cut do together, the volume warnings a `minimum_week` trips.
- **Scheme registry** (#28): which schemes declare `training_max`.
- **Schema**: `override` rows on the WeekPlan (kind, scope refs, params, reason triple), the
  `decision` table with kind, params, `until`, `superseded_by` and the retire link, and the
  Decision-kind registry as a table the contract tests read.
- **Migration**: old `[caps]` to `safety_ceiling`, old `[cardio]` run caps to `activity_cap`,
  the two parked conditioning sessions to `park_session`, open standing overrides to
  `override` Decisions with their until dates.
