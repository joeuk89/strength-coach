# Goals: how the athlete's goal reaches the coach and the program

Spec for wayfinder #25. The research behind it is `goal-programming.md` (what each goal changes
in a program, with evidence) and `training-level.md` (how coaches define level, detect
graduation and plan long term). The decision is ADR 0014; the nouns are in `GLOSSARY.md`.

The shape in one paragraph: the athlete has one current **Goal** (a record: kind, priority
lifts, milestones, the why). Each **Program version** carries an **emphasis** chosen from it,
and at adoption the version's `[dose]` and `[deload]` are filled from the emphasis when unsaid
and written into the version, so the weekly rule reads the version and never the Goal; each
line's scheme, RPE and rest are the `program` skill's judgement, and adopt warns where they sit
outside the emphasis band. A **Phase** (deficit, maintenance,
surplus) is the one long-range structure that outlives a block; it tilts the defaults and sets
the bodyweight trend the week is checked against. At each block boundary a derived progress
report shows the coach where the athlete stands against the Goal, with per-lift **cadence
signals** in place of a stored training level. Code reads the Goal at two moments, adopt and
the block boundary (`coach progress`); it reads the Phase there and at every `checkin open`, for
the trend and the until condition (**What the Phase changes**); the coach reads both whenever a
judgement is made.

## The nouns

### Goal

One current row; `goal adopt` records a new one and marks the previous `superseded`. Rows are
immutable.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `hypertrophy` or `strength` | What the athlete is training for. Maintenance is an emphasis, not a goal (ADR 0014) |
| `priority_lifts` | ordered list of Exercise refs, may be empty | The lifts the athlete is judged on by e1RM. A `hypertrophy` goal with priority lifts is what coaches sell as powerbuilding |
| `milestones` | list of Milestone | See below |
| `why` | text | The look, the reason, the long-term direction in the athlete's words. Shown to the coach, never parsed |
| `because` | text | Why this row supersedes the previous one; "first goal" at onboarding |
| `adopted` | date | |
| `status` | `current` or `superseded` | Derived from being the newest row; stored for the export |

### Milestone

A strength target on one exercise with no date. A dated target is a Follow-up (ADR 0009).

| Field | Type | Notes |
| --- | --- | --- |
| `exercise` | Exercise ref | Need not be a priority lift (the gym-only deadlift) |
| `target.kind` | `e1rm`, `load_x_reps`, `bodyweight_multiple` | |
| `target.value` | `e1rm`: a load in athlete units; `bodyweight_multiple`: a multiple | A bodyweight multiple is read against the 14-day Weigh-in average on the exposure's date (the 14 days are opinion) |
| `target.load`, `target.reps` | `load_x_reps` only: a load in athlete units (0 for an unassisted bodyweight lift) and a rep count | The example below; `schema.md`'s CHECK follows this shape |

**Reached** is derived: the first Exposure whose e1RM (or logged load for reps) meets the
target, with its date. Never stored. The progress report shows it as a figure; there is no
`milestone_reached` code (`week.md`). With fewer than two weigh-ins in the 14 days before an exposure, a
bodyweight multiple is "not computable" and shown as such (two weigh-ins is opinion).

### Emphasis

A field of the Program version, `hypertrophy`, `strength` or `maintenance`, replacing the
former `goal` field (ADR 0009, amended). It fills the version's dose and deload when unsaid, sets
the band each line's scheme, RPE and rest are checked against, and sets what the week is checked
against. `maintenance` keeps the Goal's schemes and intensity and cuts
the dose; it has no schemes of its own, which is why it cannot be a Goal kind.

### Phase

A ledger record, one open at a time.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `deficit`, `maintenance`, `surplus` | |
| `rate_pct_bw_per_week` | number | Intended bodyweight change; negative in a deficit. Optional in the Draft: the kind's default (**What the Phase changes**) is filled into the row |
| `until.kind` | `date`, `bodyweight_at_or_below`, `bodyweight_at_or_above`, `coachs_call` | |
| `until.value` | date or bodyweight in athlete units | Absent for `coachs_call` |
| `opened`, `closed` | date plus the Check-in or Goal row that did it, and a reason | |

Opened and closed inside a `checkin record` file or a `goal adopt` draft; the athlete's yes to
that file is the confirmation. No `phase` verb. A reached `until` condition raises
`phase_condition_met` at the next check-in; it never closes the phase on its own. Bodyweight
conditions read the 14-day Weigh-in average. No waist or body-fat condition in v1 (nutrition is
out of scope, ADR 0004).

## Writing a Goal

`goal adopt <draft>` validates a Draft and records the row. It is a plain store write, not an
asked verb, because nothing leaves the store; `publish` commits the export as usual. The
`onboard` skill writes the first Goal before the first program; the `program` skill writes a new
one when the athlete's aim changes. The Draft:

```toml
kind = "hypertrophy"
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
```

`goal adopt` refuses an unknown exercise, a duplicate priority lift, a milestone with no target,
and a second open Phase. It records the diff from the previous Goal in the envelope.

## Defaults per emphasis

What the emphasis means for a version. Two rows are **filled** by `adopt` when the Draft leaves
them unsaid, Weekly dose into `[dose]` and Deload into `[deload]`, because each has one
defensible number. Every other row is a band the `program` skill **proposes** from and `adopt`
**warns** against: scheme, RPE and rest are authored on every line (`program.md`), never filled,
because choosing them is coaching judgement with a reason (an assisted lift, a rack too coarse
for `top_backoff`, one more block of `linear`) and the bands below are ranges, not numbers.
Citations are to the research notes (`rn:goal-programming §n`); each number is marked evidence
or opinion there.

| Knob | `hypertrophy` line | priority lift (any goal) and `strength` line | `maintenance` version | Source |
| --- | --- | --- | --- | --- |
| Reps and intensity | 6–15 reps at a target RIR; load follows reps | 1–6 reps at 80 % 1RM or above | the Goal's scheme, unchanged | §1, evidence |
| RIR | stimulus dial: the line's authored RPE stands every week (default 8, 2 RIR); the walk toward failure happens as double progression adds reps at a held load, not as a coded rule (`prescription.md`) | fatigue cap: top set RPE 8–9 (1–2 RIR), back-offs RPE 5–6 | the Goal's RIR | §2, evidence on direction, opinion on numbers |
| Weekly dose | 10–20 hard sets per muscle; the version stores one target, default 10 rising toward 20 as blocks accumulate | 5–15 hard sets per lift, floor 2–6; default 8 (opinion). A lift's counted variants add their hard sets to its figure (`program.md`, "Dose and deload") | one third of the Goal's target, floor one hard set per exercise per week; intensity held | §3, evidence |
| Scheme the skill proposes (`scheme_off_emphasis` band) | `double_progression`; `assistance_ladder` on an assisted bodyweight lift | `top_backoff` on a load-bearing lift; on a bodyweight lift `assistance_ladder`, then `double_progression` in a 3–6 range once unassisted | the Goal's scheme, dose cut | §4, opinion resting on Helms 2018, Hickmott 2022; `rn:progression-methods §3` |
| Stall signal (per line, `prescription.md`; several stalled lines read as one muscle behind is the `program` skill's judgement from `coach progress`) | reps at the authored RPE flat on the line | e1RM flat or falling over the exposures the Weekly prescription ticket defines | strength on the kept lifts falls over a block | §5, opinion |
| Deload | `set_cut_pct` 40, `load_cut_pct` 0, `rpe_cap` 8: cut sets, hold load | `set_cut_pct` 30, `load_cut_pct` 0, `rpe_cap` 8; `test_priority_lifts` prescribes a **test** single on each priority lift in the light week, whose result may become the next block's training max | no planned deload | §6 and rn:deloads.8 to .10, evidence that intensity is held; the percentages are this framework's defaults (opinion) |
| Order | free; chosen for fatigue and preference | priority lift first in its session | as the Goal | §7, evidence |
| Rest | 1.5–3 min | 2–5 min | as the line's load | §9, evidence; rest follows load, not goal |

Two rules that follow:

- A `hypertrophy` version with priority lifts gets the hypertrophy column everywhere except on
  the priority lifts, which get the middle column, including the test single in the light week.
- `linear` and `wave_531` are never proposed by this table. `linear` is the novice pace and no level is stored
  (ADR 0014); a coach names it, or moves a lift to it on `cadence_fast`. `wave_531` is the
  answer to `cadence_slow` on a `top_backoff` lift. Whether a dumbbell rack's steps are too
  coarse for `top_backoff` is the coach's judgement at authoring, not a check: a priority lift
  named `double_progression` in a 3–6 range is inside the expected band and raises nothing.
- A `strength` version has priority lifts by definition; `adopt` refuses one with none
  (`priority_lifts_required`). Its non-priority lines default to the hypertrophy column, which
  is what every strength template does with its accessories.

### What the Phase changes

Opinion, from Israetel and Helms (`rn:training-level §4`): a surplus moves the proposed dose up
within its band, a deficit keeps it (both sources keep volume in a deficit), and no Phase moves
the intensity.

| Phase | Dose default | Default rate (% BW per week) | Trend band |
| --- | --- | --- | --- |
| `deficit` | the emphasis default, held: volume is kept in a deficit and intensity held so strength is kept | −0.5 | within ±50 % of the target rate |
| `maintenance` | the emphasis default | 0 | ±0.25 % BW per week |
| `surplus` | upper half of the band | +0.25 | within ±50 % of the target rate |

The default rates are the conservative end of each cited range (`rn:training-level §4`): loss
0.5–1 % a week to keep muscle (Helms), gain 0.5–1.5 % a month (Helms) and 0.15–0.8 % a week for
an intermediate (MacroFactor). The band half-widths are the engine's opinion under the same
citation. Both live in the phase registry (`coach schema --registry phase`), beside the kinds.

The observed rate is the change between the current 14-day Weigh-in average and the one 28 days
earlier, per week; `checkin open` compares it once the Phase has 28 days of weigh-ins and raises
`phase_trend_off` (phase id, target rate, observed rate, window) when it falls outside the band.
It is a warning at the check-in, resolved by the coach's read (diet is out of scope; the engine
states the fact). The card carries the Phase line it reads from (`check-in.md`).

## Adopt: the goal checks

Added to whatever Program authoring specifies. One violation, the rest warnings left by an
Acknowledgement in the program Draft and frozen on the version, with the same identity rules as
plan warnings (`validation.md`); scope `version` is the program version id.

| Code | Severity | Scope | Params | Cleared or left by |
| --- | --- | --- | --- | --- |
| `goal_missing` | violation | version | none | `goal adopt` |
| `priority_lifts_required` | violation | version | emphasis | a Goal with priority lifts, or a different emphasis |
| `emphasis_off_goal` | warning | version | goal kind, emphasis | Acknowledgement (a planned maintenance or strength block under a hypertrophy goal is legitimate) |
| `scheme_off_emphasis` | warning | line | line scheme, emphasis, expected band | Acknowledgement, or the line naming a fitting scheme. Band: hypertrophy line `double_progression`, `assistance_ladder`, `hold`; priority lift or strength line `top_backoff`, `wave_531`, `linear`, `assistance_ladder`, or `double_progression` with a rep range inside 3–6 |
| `priority_lift_absent` | warning | priority_lift | exercise id | Acknowledgement, or a line for it |
| `priority_lift_not_first` | warning | session | exercise id, position among the session's lines that carry a working group (an activation-only or warm-up line never counts) | Acknowledgement, or reordering |
| `dose_off_band` | warning | dose | muscle or lift, target, band, phase | Acknowledgement, or a target inside the band |
| `counted_variant_off_pattern` | warning | counted_variant | lift, counted variant, the two patterns, the two primary muscle lists | Acknowledgement, or a variant sharing the lift's pattern and primary muscles |
| `deload_off_emphasis` | warning | version | deload policy, expected shape | Acknowledgement, or the expected shape |
| `scheme_change_off_signal` | warning | line | previous scheme, new scheme, signal key or none, `may_schemes` | Acknowledgement, or keeping the scheme, or a scheme the signal lists (**Response to a cadence signal**) |

The filled defaults appear in the adopt diff, so the athlete sees what the emphasis chose.

## What reaches the weekly loop

Nothing reads the Goal weekly: the prescribe request (`prescription.md`, **What prescribe is
handed**) carries the version and never the Goal or the Phase (ADR 0003, amended). The
goal-specific weekly behaviour is a property of the scheme the version names:

- the dose check against the version's per-muscle target and, for priority lifts, the per-lift
  target with its counted variants (ADR 0009, extended): the card's Dose line and the plan
  warnings `dose_under_target`, `lift_dose_under_target` and `session_dose_high` (`week.md`);
- no coded RIR walk and no coded set ramp: the authored RPE stands, and sets are added by the
  agent through `restate_sets` or the next version when the dose check shows a muscle under
  target (`prescription.md`);
- strength lines holding RIR as a cap and moving load from e1RM;
- the stall signal each scheme watches (`stall_streak`: three ordinary exposures with no gain on
  the scheme's metric, reps at the authored RPE on a hypertrophy line, e1RM on a strength line;
  `prescription.md`).

So a change of goal reaches the week only through a new Program version, which is the one
place a coach would look for it.

## The block boundary

The block boundary is the check-in whose closed week ends the Block by its derived kind (`light`,
`return` or `missed`, `week.md`), or the adoption of a `redesign` version (ADR 0015); there is
no block reset Decision (`overrides.md`). The `program` skill runs
then, and a deep check-in reads the same report.

### `coach progress`

A read verb, derived from the store, rendered to `pages/progress.md` at `publish` (ADR 0012).
Compact summary by default; `--full` adds per-line history.

| Section | Content |
| --- | --- |
| Priority lifts | per lift: e1RM now, change over the closed block and over the last three, best load for reps, stall streak and resets under the current scheme, cadence signal if any |
| Milestones | per milestone: distance (load, reps or ×BW to go) or the date reached |
| Dose | per muscle and per priority lift: hard sets achieved against target, by week of the block |
| Adherence | core sessions by tier, misses by tag |
| Phase | kind, target rate, 14-day bodyweight trend against it, the `until` condition and whether it is met |
| Goal | kind, adopted date, `why` verbatim |

### Cadence signals

The replacement for a stored training level (`rn:training-level §2`, thresholds opinion). Per
exercise, raised at the block boundary, scope `exercise`, cleared by a new Program version
or left by a `leave_warning` Decision. The condition is per scheme, as the stall metric is
(`prescription.md`), because each scheme's cadence is read on its own metric: a 12–15-rep
`double_progression` line never yields an e1RM point and a `top_backoff` line has no rep range.
Every row requires adherence at or above the floor (`week.md`) over the blocks it reads.

| Code | Line's scheme | Condition over the closed block and the one before |
| --- | --- | --- |
| `cadence_slow` | `linear` | two resets on the line under the scheme within the two blocks |
| `cadence_slow` | `double_progression`, `assistance_ladder` | a `stall_streak` open on the line at the end of both blocks (no gain on the scheme's metric across them) |
| `cadence_slow` | `top_backoff`, `wave_531` | a non-positive exercise-wide e1RM slope across the two blocks |
| `cadence_fast` | `double_progression` | every exposure in the closed block hit the top of its rep range at or under the authored RPE, with no stall |
| `cadence_fast` | `top_backoff` | the one-row cap bound on every exposure in the closed block: the model asked for more than a row each time |
| `cadence_fast` | `linear`, `hold`, `assistance_ladder`, `wave_531` | never raised: on `linear` the pace is already right; the others have no faster scheme to propose |

A reset is the stall move the weekly rule records; its definition is the Weekly prescription
ticket's. The signal never carries the words novice, intermediate or advanced; those stay
prose. The response is always a new Program version with a Decision citing the warning (a slower
or faster scheme on that lift, a different progression cadence), never an automatic change.

Each signal carries its row of the switching table below in `params`: `may_schemes` (the
schemes the line may move to, machine-read by `adopt`), `may` and `never` (short phrases the
coach reads and quotes). That is how the rule reaches the agent: a running agent reads no table
(ADR 0020).

### Response to a cadence signal

The scheme-switching rule is an engine table in `core`, `(signal, scheme) → may_schemes, may,
never`, with its `rn:` citations; this section is its spec, as `schema.md` is `schema.sql`'s. The
`program` skill's Judge answers a signal only with a move the flag lists and carries no table
(`skills.md`, ADR 0020). A scheme changes only when its cadence has run out, which is what the
signal says: the switch under `linear` is the second reset, per lift, and there is no second count
(`rn:progression-methods §4`, the switching table; Starting Strength's end of the one-to-three
range, matching `cadence_slow`). Within a block the weekly rule answers a stall with its own
reset; the boundary is where the scheme may change.

| Signal | Line's scheme | The version may | Never |
| --- | --- | --- | --- |
| `cadence_slow` | `linear` | move the line to `double_progression` (hypertrophy line) or `top_backoff` (priority lift or strength line) | keep resetting |
| `cadence_slow` | `double_progression` | add sets early in the next block, plan the deload, swap the exercise or change the rep range at the boundary | change the scheme: no source does |
| `cadence_slow` | `top_backoff` | move the lift to `wave_531`, the training max set by the test set or a `training_max` Decision; or change back-off volume and add a variation first | drop to a hypertrophy scheme to escape a strength stall |
| `cadence_slow` | `wave_531` | lower the training max about 10 % by Decision and stay a cycle; the scheme stands | raise the training max to chase the miss |
| `cadence_slow` | `assistance_ladder` | hold the rung; at zero assistance move to `double_progression` on reps | skip rungs |
| `cadence_fast` | `double_progression`, `top_backoff` | propose `linear` on that lift while the rack has a next row; the signal is the evidence, no stored level is needed | fill `linear` without a Decision |

`adopt` holds the rule with one warning, `scheme_change_off_signal` (scope line): a line whose
scheme differs from the previous version's line for the same exercise id, in any session, and
either no cadence signal is open on that exercise or the new scheme is outside the signal's
`may_schemes`. A line whose exercise the previous version did not carry raises nothing. It runs
on `amend` and `redesign` alike and is left by an Acknowledgement like the other adopt warnings:
a coach may change a scheme for a reason the signal cannot see.

Two signals that look like a stall and are not: RPE rising at a held load on many lines is
fatigue, answered by the deload policy; RPE rising or pain on one line is technique or a
niggle, answered by a swap or a Niggle, never a scheme.

### Other flags the Goal and Phase raise

| Code | Raised by | Scope | Params |
| --- | --- | --- | --- |
| `phase_condition_met` | `checkin open`, every check-in | instance | phase id, condition, value |
| `phase_trend_off` | `checkin open`, every check-in | instance | phase id, target rate, observed rate, window |

## What the skills ask, judge and explain

One table so the four moments are seen together; nothing reads it at runtime (ADR 0020). The
`check-in` asks row is the card builder's: `checkin open` reads the version's emphasis and
priority lifts and asks accordingly (`check-in.md`). The other rows are each skill's own Judge,
which carries its column in its own words inside its budget (`skills.md`). Each cell is the whole
of what the emphasis changes.

| Moment | `hypertrophy` | priority lifts and `strength` | `maintenance` |
| --- | --- | --- | --- |
| `check-in` asks | reps and RIR on the lines that moved; pump and soreness as a dose read | the priority lifts first: did the top set move, how did it feel, any grind | whether the kept lifts held |
| `plan-week` judges | dose attainment against target; a flat line early in a block wants sets (`restate_sets`), late wants the deload | e1RM trend on each priority lift; fatigue against the RIR cap; a flat block is normal, not a crisis | nothing weekly beyond the recovery ceilings |
| `plan-week` explains a line as | last week's reps at the authored RPE, from the derivation steps | e1RM times the scheme | held |
| `program` at the boundary | reads `coach progress`: dose achieved, muscles behind target, cadence signals; proposes next block's sets and any swap, never a scheme change on a stalled `double_progression` line | reads `coach progress`: e1RM over three blocks, milestones, cadence signals; proposes scheme changes on signalled lifts per **Response to a cadence signal**, a test week result as the training max | whether to return to the Goal's emphasis |
| `onboard` and `program` write | the Goal, the Phase and the `why`; the long-term direction in the profile prose | | |

The Profile adds the why and the long-term direction in words; never a number the Goal already
holds.

## Worked example: the carried-over athlete

Goal `hypertrophy`, priority lifts bench and strict pull-up, milestones as in the Draft above,
Phase `maintenance` until coach's call. The `program` skill authors version 1 with emphasis
`hypertrophy`: `double_progression` at the authored RPE 8 on every hypertrophy line, `top_backoff`
on bench, the `assistance_ladder` on the pull-up while it is assisted (the band's bodyweight
column); adopt fills 10 sets per muscle, 8 sets per week on bench and the pull-up, and a 40 % set
cut with load held, under which the light week prescribes a test single on bench alone (the
pull-up is under neither `top_backoff` nor `wave_531`, `prescription.md`); it warns
`priority_lift_not_first` if the pull-up sits after rows. At the
first block boundary `coach progress` shows bench e1RM over the block, the pull-up's best reps,
dose by muscle, the flat bodyweight trend, and no cadence signal; the `program` skill proposes
block 2. Two blocks later a `cadence_slow` on bench, its `may_schemes` naming `wave_531`, is
answered by a new version with that scheme on bench, the Decision citing the warning and its `rn`.

## Handed to other tickets

- **Program authoring** (#22): the authored form carries `emphasis`; the defaults table above
  is what adopt fills (`[dose]`, `[deload]`) and warns against (the rest); the `test` set type ships; the adopt checks above join its list.
- **Weekly prescription** (#26, settled in `prescription.md`): the stall and reset per scheme
  that `stall_streak` and `cadence_slow` read; no coded RIR walk or set ramp; the training max
  is never moved by the rule (`training_max_due` asks for a Decision).
- **Verb set** (#16): `goal adopt` (plain write) and `coach progress` (read).
- **Override catalogue** (#19): the test week needs no override; it is the deload policy.
- **Schema** (settled in `schema.md`): `goal`, `goal_priority_lift`, `milestone` and `phase` tables; `emphasis` on the version and `priority_lifts` read from the current Goal at adopt, never copied;
  the two new scope kinds (`version`, `exercise`) in the flag registry.
