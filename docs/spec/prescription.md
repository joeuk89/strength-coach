# Weekly prescription: how last week's exposures move this week's dose

Spec for wayfinder #26, decided 2026-10-31. The decision behind the pipeline is ADR 0017; the
pure function and the freeze at approval are ADR 0003; the hard and warning line is ADR 0005;
the schemes that exist are `program.md`'s; the override kinds are `overrides.md`'s; the
rounding and the ladder are ADR 0008's. Flag codes raised here are rows in `validation.md`.
Nouns are in `GLOSSARY.md`.

The shape in one paragraph: for every line of every planned session, `prescribe` picks one
**anchor exposure**, lets the line's scheme move the dose from it, applies the plan's line
override and any override Decision in force, applies **one** cut (the return band or the light
cut), then the niggle constraints, the RPE ceilings, the safety ceiling and the rack, and finally
derives the warm-ups. Each step is recorded as a **derivation step** (step, from, to, cause), so the agent
reads why a line landed where it did instead of a prose rationale. The rule never writes a
number the agent did not ask for: it holds and warns where the old engine guessed.

## What prescribe is handed

`prescribe` is a pure function of one immutable **prescribe request**, assembled by the shell
(`plan draft`, `plan apply --dry-run`) from the store for the planned date. This list is the
only place the request is stated; the ADRs that name `prescribe` point here (ADR 0003, 0005,
0016, 0017). The request is rebuilt on demand and never stored: the approved WeekPlan freezes
the prescriptions and their derivation steps, not the inputs (ADR 0003). It is a code type, not
a glossary noun.

| Input | Read by |
| --- | --- |
| the Program version (the form with its filled `[dose]`, `[deload]` and session `minutes`) | every step; the scheme's hit test reads the authored groups |
| the Exposures | the anchor, e1RM, days off, stalls |
| the plan's typed overrides | step 2, the week override before any line derives |
| the Decisions in force on the planned date: `override`, `safety_ceiling`, `training_max`, `ladder_rung`, each with the date it was recorded on | steps 3, 7, the `wave_531` scheme and the `exercise_ladder` standing rung |
| the open Niggles' constraint rows | step 5 |
| the status spans (`no_training`, `ill`) | which sessions derive; days off; the illness cap |
| the rack snapshot per location (ADR 0008) | steps 7 and 8, every load step |
| the Block's hard-week count | the `wave_531` wave |
| the latest redesign's adoption date | stalls (none before it count) |
| the version's own adoption date | an `exercise_ladder`'s first rung's start |
| the last matched Activity per conditioning session | the session schemes |
| the planned date | everything dated |

Never in the request: a WeekPlan (ADR 0005), the Goal or the Phase (ADR 0014), the profile,
a Weigh-in. The goal reaches the week only through the version it shaped; a bodyweight line
carries no load, so nothing here reads bodyweight.

## The anchor exposure

Per line, in this order:

1. The newest Exposure of the line's exercise **in the same session id**, skipping any
   exposure matched to a planned session in a `light_week` (deload logs are never a baseline).
   A return-week exposure is kept, including one from a line that took the return band inside
   a light week: the return week's logs are the baseline for the week after (ADR 0005: no 43+
   re-test rule).
2. If none in the last 90 days (two Blocks at the default ceiling; opinion): the newest exposure
   of the exercise in **any** session (a redesign with new session ids, a swap, a new line of an
   exercise already trained).
3. If none: the line's `start_load` (or the `swap_exercise` override's) and the scheme's
   opening position (`program.md`, the scheme table). A load-bearing line with neither is
   `start_load_missing`.

A lifting or rehab line never anchors on an Exposure from a workout matched to a conditioning
session, by any step, and the e1RM window below never reads one: those sets anchor their own
session's lines and nothing else (ADR 0010). A conditioning line's `hold` anchors within its own
session by step 1, and with no history of its own falls through to steps 2 and 3 as any line.

On a line in a rack mode (`total`, `per_hand_x2`, `single_implement`), steps 1 and 2 also skip
an exposure with no working set at a positive load (a logging gap, such as a carry logged at 0):
it has no usable anchor load, so the next older exposure anchors, and with none, step 3 applies.
The line warns `anchor_load_unusable` naming the newest skipped exposure, its logged load and
the anchor used. Under assistance 0 is a real load (no assistance) and is never skipped. The
skipped exposure still counts as a day trained: days off per lift read its date as before.

e1RM is always exercise-wide: the best qualifying point in the 42 days before the planned date
(one Block at the default ceiling, rn:deloads.3; the window is opinion), every session included.
A qualifying set has 12 or fewer reps to failure, reps plus 10 minus RPE (rn:autoregulation.5).
A newer exposure with more than 12 reps to failure at or above that point's load invalidates it
until a newer qualifying point exists.

**The anchor's load.** The anchor's top working load, as logged. A logged load that is not a row
of the session location's rack is replaced by the nearest row **at or below** it, and the line
warns `offgrid_anchor_ignored` naming both. A historical load never defines the grid. A zero
logged load on a line in a rack mode never anchors (the skip above), so it never snaps to the
rack's bottom row.

**Days off per lift** = `max(layoff, exposure age − usual interval)`, where the layoff is the
gap since the last lifting exposure of any kind (coach-led counts), the usual interval is the
median of the lift's last four gaps clamped to 7–14 days (opinion), and 10 days of grace apply
before a lift counts as decayed (the band with no change, rn:detraining-return.3). `no_training` status spans count as days off. A `trained_unlogged`
Annotation on a planned session, or a hand-entered Workout with no sets (`week.md`), counts as a
lifting exposure **date** for every line of that session: it resets the layoff and those lifts'
exposure age, carries no load and never anchors. Nothing else moves days off.

**What the hit test compares against.** `prescribe` cannot see any WeekPlan (ADR 0005), so a
scheme judges the anchor against the **program version's authored** reps, range and RPE for the
line, as amended by an override Decision in force on the exposure's date. A past plan's
`restate_sets` or `pin_load` does not enter the test. Two shared rules:

- Fewer working sets logged than the authored count: not a hit, hold, no flag (the check-in's
  against-the-prescription report says so). Extra logged sets are ignored.
- A logged set with no RPE counts as on target. In the e1RM it yields a lower bound.

## The move, per scheme

Every step in load is at most **one rack row** on the session location's rack for the
exercise's equipment kind (grid increment at a grid location). No scheme has an `increment`.
No scheme changes the set count: sets come from the version, a `restate_sets` override or the
cut.

| Scheme | Reads from the anchor | Hit | Move on a hit | Under | Over |
| --- | --- | --- | --- | --- | --- |
| `double_progression` | reps and RPE per working set | every working set reached the top of its range at or under the authored RPE | load to the next rack row; reps back to the bottom of the range | hold load and range | a set at RPE ≥ authored + 2, or below the bottom of the range: hold and warn `rep_range_missed`. The rule never cuts |
| `linear` | reps per working set at the anchor load | every working set at the authored reps at or under the authored RPE | load to the next rack row | a short attempted set is a **miss**: hold. A set never logged is incomplete, not a miss | see **Stalls**: the second consecutive miss at one load resets |
| `hold` | nothing | | the authored sets at the anchor load (`start_load` with no anchor) | | |
| `assistance_ladder` | reps and RPE per set on the current rung | every working set at the group's reps at or under its RPE | one rung up (less assistance); hold at the last rung | hold the rung | hold the rung and warn `rep_range_missed` on a set at RPE ≥ the group's RPE + 2 |
| `exercise_ladder` | the standing rung (below), its exercise's ordinary exposures from the rung's start, its `start_load` on a load-bearing rung | the rung's advance criterion (`program.md`) on its run of the newest exposures | never moves: warn `rung_met` naming the next rung, or `ladder_top` on the last; a `manual` rung raises neither | hold the rung | hold the rung |
| `top_backoff` | the exercise's best e1RM in the window, or the carried e1RM while it binds (**The carried e1RM**, below) | not a hit test: the top load is `load_for(e1RM, reps, rpe)` of the top group (the first working group, `program.md`) rounded down, **capped at one rack row above the heaviest top load in the e1RM window (the anchor's included; while the carried e1RM binds, the pre-layoff heaviest top × the band factor too)**; every later working group is a back-off at `pct_of_top` of the top, rounded nearest | | no e1RM in the window and no carried e1RM: hold the anchor's top load and warn `no_e1rm` | a top set logged above the model raises the e1RM; nothing else |
| `wave_531` | the current `training_max` Decision (`start_load` until one exists), the Block's hard-week count and the last rep-out | the wave is `hard weeks completed in the block mod 3`; loads are the wave's percentages of the training max rounded down; the last working set is open | | a rep-out below its wave's reps: warn `rep_range_missed` | after the third wave is logged at one training max: warn `training_max_due` with the three rep-out counts. The rule **never** moves the training max; the agent records a `training_max` Decision: the published step, 2.5 kg upper body or 5 kg lower body, in athlete units (rn:progression-training-age.9), or about 10 % down (rn:progression-methods §4) |

Citations: `double_progression` rn:progression-training-age.2; `linear` rn:progression-training-age.3;
`assistance_ladder` and `exercise_ladder` rn:bodyweight-skill-progression.3; `top_backoff` rn:progression-training-age.6
and .8, rn:autoregulation.1; `wave_531` rn:progression-training-age.9. The one-row cap, the
"RPE 2 over" test and `load_for` rounding down are this framework's (opinion). The catalogue
behind the registry is rn:progression-methods §1 and §2.

Notes:

- The one-row cap on `top_backoff` is a rule, not a warning: a bigger jump is the model
  over-reading one great day. Because every scheme's own step is at most one row,
  `increment_over_step` fires only on a `pin_load` more than one row above the anchor. After a
  return week the cap counts from the pre-layoff heaviest top scaled by the band, so the line
  gets back to its pre-layoff level in about one week rather than one row a week.
- `top_backoff` reads the **best** point in the window, so one bad day never drops the top set;
  only a recovery ceiling or the window expiring lowers it.
- When the e1RM moves the `top_backoff` top (the one-row cap does not bind), the `scheme` step
  records `cause = e1rm <exposure ref>`, the exposure the e1RM came from (the pre-layoff one
  while the carried e1RM binds), and the line's `change` ends with it (below).
- With no next rack row (a band at the top of its ladder, a dumbbell rack's heaviest pair) a
  hit holds and the step records `cause = rack_top`; the agent swaps or the version changes.
- A `test` single is never authored; the deload policy prescribes it in a light week, below.
- A `hold` override replaces the scheme's move only: the cut, constraints and
  ceilings still apply to a held line.
- Conditioning sessions carry a session scheme and read the last matched Activity:
  `emom_density` at or under `rpe_target` → `minutes + minutes_step` up to `minutes_cap`, then
  one rep per exercise up to `reps_cap`; over target → hold. `circuit_rounds` → one round up to
  `rounds_cap`, then reps. No Activity → the params as authored. Their lines run `hold`.
- An `exercise_ladder` line stands on the rung its `ladder_rung` Decision names (`overrides.md`),
  or the first with none, and prescribes that rung's exercise, cues and working group (ADR 0023),
  and on a load-bearing rung its load (`program.md`, **Start loads**; ADR 0025).
  The rung's start is the Decision's date, or the version's adoption for the first rung; the
  criterion and `stall_streak` read only exposures of the standing rung's exercise from it, and
  exposures on another rung's exercise, or on its own before its start, count for nothing, so two
  rungs may share an exercise (ADR 0025). The line's key stays its first rung's exercise for
  every flag and override; the prescription and history matching carry the standing rung's. A
  light week holds the rung with its sets cut. The climb is the agent's: a `ladder_rung` Decision
  after the athlete's yes.

## Stalls

One definition: three consecutive ordinary exposures of the line (light-week and return-week
exposures skipped) with no gain on the scheme's metric raise `stall_streak` with the three
exposure refs. Three is opinion: the sources say read the trend, not one session, and name no
count (rn:progression-methods §4). A line in a `practice` session raises none, and the progress
view shows its streak as 0. It never resets either: a reset is a judgement on failed progress and
a practice is never judged, so a `practice` line on `linear` holds through its misses and the
progress view shows its resets as 0. The progress view reads a lift's streak and resets on its
first line in a judged session, from the exposures matched to that session or to none.

The streak reads exposures on or after the latest redesign's adoption date and none before it: a
redesign starts every line with a clean streak, because a stall under the old design says
nothing about the new one. An amend (a swap, a fix, a scheme change) leaves the streak alone, as
does a light, return or missed week; the streak spans the light week by skipping its exposures,
and `cadence_slow` relies on it surviving the Block boundary (`goals.md`). The metric per scheme:

| Scheme | Metric | The rule's own response |
| --- | --- | --- |
| `double_progression` | total reps at or under the authored RPE at the anchor load | none: hold. Sets, a deload or a swap are the agent's (`goals.md`, the cadence table at the boundary) |
| `linear` | a miss | the **reset**: the second consecutive miss at one load (`misses_before_reset = 2`, Starting Strength's "the 2nd time in a row", rn:training-level §2) sets the load to `reset_factor` × the anchor load, rounded **down** to the rack. Both are `linear` params (`program.md`); the registry default `reset_factor = 0.9` is the over-40 reset (5 % under 40, 10 % over 40, rn:training-level §2), so a coach names `reset_factor = 0.95` on the line for a younger athlete. The miss count restarts once an exposure at a lighter load is logged. Resets per lift are derived from history; `cadence_slow` reads them |
| `assistance_ladder` | the rung | hold the rung |
| `exercise_ladder` | total reps, or seconds on a duration rung, at or under the authored RPE on the standing rung, reading only exposures since the rung's start | hold the rung |
| `top_backoff` | e1RM | none: the model holds the top set |
| `wave_531` | the rep-out's e1RM (counts fall wave to wave by design) | none: `training_max_due` or `rep_range_missed` says what happened |

A stall is a warning the agent judges within the block; the scheme may change only at the block
boundary (`goals.md`, **Response to a cadence signal**). RPE rising at a held load on many lines
is fatigue, not a stall, and is the deload policy's.

## The pipeline

ADR 0017. Each step runs once, in this order, and records `(step, from, to, cause)` on the line
when it changed anything. No step may raise a load a previous step lowered.

Before any line derives, the plan's week override and the status spans choose **which sessions
derive and where**: a `no_training` span covering the whole week plans nothing (`week.md`'s
`break`); a `minimum_week` override derives only the kept sessions; a `one_off_week` override
with a `location` derives every session there. These choose sessions, never numbers: a kept
session in a minimum week still takes its return bands, illness caps and niggle constraints.

| # | Step | Reads | Does |
| --- | --- | --- | --- |
| 1 | `scheme` | the anchor, the version's line | the move above |
| 2 | `override` | the plan's line override | `swap_exercise` re-runs step 1 on the other exercise; `pin_load` replaces the working load (grid and ceilings still apply); `hold` repeats the anchor's dose; `restate_sets` replaces the set groups; `drop_line` ends the line |
| 3 | `decision` | override Decisions in force on the planned date | the same kinds; the plan's override wins on the same kind and line |
| 4 | `cut` | the lift's days off, the plan's `light_week` override | exactly one of: the return band, the light cut, nothing (below) |
| 5 | `niggle` | open Niggles | constraints, strictest binds (below) |
| 6 | `rpe_ceiling` | the return band, the light week's `rpe_cap`, illness, niggle caps | every capped set's load limited through the e1RM model (below) |
| 7 | `rack` | the location's rack, a `safety_ceiling` Decision | the safety ceiling truncates the rack; the load rounds to a row (ADR 0008: nearest by direction; a cut rounds to the nearest row no heavier than its target) |
| 8 | `warm_up` | the first working set's load | the registry ramp, then the ADR 0008 ladder (below) |

Ceilings never compose: a load cap from a niggle, a safety ceiling, an illness RPE cap, the
light week's RPE ceiling and a `pin_load` all bind by `min`. A step that found a stricter
ceiling already binding records `cause = not_binding`.

### The cut

Step 4 applies exactly one cut per lifting line, the first that holds:

| Order | Cut | Holds when | Does |
| --- | --- | --- | --- |
| 1 | the return band | the lift's days off > 10 | the band, below |
| 2 | the light cut | the plan carries `light_week` | `set_cut_pct` off each working group's sets (rounded, min 1), `load_cut_pct` off the working load step 1 produced, rep-outs closed; the policy's `rpe_cap` is a ceiling in step 6 |
| 3 | none | otherwise | |

The return band wins because it is measured from the pre-layoff anchor; a light cut on top of it
is the #257 shape (ADR 0017, amended). A line that took the return band inside a light week is a
return line: its exposure anchors next week, where a light-week exposure would not.

The light cut's shape is the version's `[deload]` table (`set_cut_pct`, `load_cut_pct`,
`rpe_cap`; `program.md`, filled from the emphasis), as restated for the week by the `light_week`
override (`overrides.md`). The load cut multiplies the working load step 1 produced (the anchor's
move, the `top_backoff` top, the wave loads of the training max), so it is defined for every
scheme, and back-offs follow their top; at 0 the load is held. A `hold` line is cut like any
other (ADR 0017).

Illness is not a cut and not a week kind here: an `ill` span since the line's anchor with no
exposure since it ended caps every set of the line at RPE 7 in step 6 (rn:detraining-return.4),
where it binds by `min` with the other ceilings.

The closed week's kind for the Block's count (light, return, break, minimum, one_off, hard,
missed, partial) is `week.md`'s read after the fact. `week.md`'s `return` is the athlete's
whole-week layoff; the band here is per lift.

### The return band

Days off per lift as above. The cut is measured from the **lower** of the scheme's proposal and
the anchor's load, so a return week never carries a progression, and from the pre-layoff
anchor only: the week after derives from the return-week exposure by the ordinary scheme, which
under `top_backoff` reads the carried e1RM (below).

The band is a safety bound (ADR 0005, amended): no override waives or softens it, and `pin_load`
lowers only. The one lawful route is the fact behind it: days off, which a `trained_unlogged`
Annotation or a hand-entered Workout moves (above). `restate_sets` may still change the set
groups of a return line, and the band's set delta then applies to the restated groups.

The bands are rn:detraining-return.3, load factors as targets before rounding:

| Days off | Load | Working sets | RPE cap |
| --- | --- | --- | --- |
| 0–10 | none | none | none |
| 11–21 | ×0.95 | −1 (min 1) | ≤ 8 |
| 22–42 | ×0.90 | −1 | ≤ 8 |
| 43+ | ×0.85 | −1 | ≤ 7 |

Per scheme: `assistance_ladder` steps back 0/1/2/3 rungs by band instead of a load cut, and
assistance is never cut; `exercise_ladder` steps back the same count of rungs (never below the
first) and prescribes the earlier rung's exercise and sets for the return weeks with the band's
set delta and RPE cap, no Decision written, its days off read across every rung's exercise; `wave_531` multiplies the training max by the band factor for the
return week only, with no rep-out set. A return line whose band, load, set delta and RPE cap do
not all derive together (an override fought the band) is `return_band_disagrees`.

Illness alone (gap ≤ 10 days) is not a cut: the RPE 7 cap is the whole return. Illness with
days off > 10 is a return line with the cap at 7.

#### The carried e1RM

After a return week, a `top_backoff` line's own 42-day window holds only the return-week sets,
which were easy, so the model alone would climb one row a week from the return load. The
**carried e1RM** lets it catch up to the pre-layoff level, discounted by the band
(rn:detraining-return.5: what is lost returns faster than it was built). It is derived on every
`prescribe` from exposures alone and never stored.

- The **return exposure** R is the lift's latest exposure whose days off on its own date
  exceeded 10. A planned date that is itself a return week carries nothing: the return week is
  unchanged.
- While R is 42 days or fewer before the planned date, the carried e1RM is the best qualifying
  point in the 42 days ending on the lift's last exposure before R (the same window rules and
  invalidation as the live read), × the load factor of the band R's days off gave (×0.95,
  ×0.90 or ×0.85). With no qualifying point there it does not exist, and `no_e1rm` behaves as
  without it.
- It **binds** while it is above the live window's e1RM. A live point at or above it, or R plus
  42 days passing, ends it.
- While it binds, every e1RM read on the line is `max(live, carried)`: the top move, the RPE
  ceilings' load limit, the test single and the `top_set_above_e1rm` check. The one-row cap
  counts from `max(heaviest top in the live window, pre-layoff heaviest top × the factor)`, the
  pre-layoff top read from the same slid window on the line.
- Every week it binds the line warns `carried_e1rm` with the pre-layoff exposure, the pre-layoff
  e1RM, the factor, the carried value and the date it expires.

Worked example: `bb_deadlift`, last exposure 2026-09-16 at 135 lb, the August best 170.5×6 @7.5
(e1RM 218.81), planned 2026-11-01 after 46 days off (×0.85). The return week cuts 135 × 0.85 as
before. The week after, the carried e1RM is 218.81 × 0.85 = 185.99, so six at RPE 7.5 asks for
144.93, rounded down; the cap is one row above 170 × 0.85 = 144.5, so the model binds. From
there the live e1RM takes over and the ordinary one-row climb resumes.

### Niggle constraints

Four kinds on the Niggle record (`niggle_constraint` rows per event, `schema.md`). The set in
force is the latest event's rows, whatever its status short of `resolved`: `reported`,
`aggravated`, `easing` and `chronic` all bind, and relaxing a constraint is an event that lists
the smaller set, never a status change. A `resolved` event carries no rows. The strictest across
every open niggle binds:

| Kind | Scope | `value` | Does |
| --- | --- | --- | --- |
| `rpe_cap` | global (no exercise, no pattern), one exercise, or one pattern | the RPE, required | caps every set's RPE; a load limit follows in step 6 |
| `load_cap` | one exercise only | the load in athlete units, required | caps the working load |
| `no_added_load` | global, one exercise, or one pattern | none | caps the working load at the anchor's top load; a floor on assistance |
| `avoid` | exactly one of exercise, pattern | none | the line is dropped by derivation |

Every row names at most one of `exercise_id` and `pattern`; `schema.md`'s CHECKs are this table.

A line over a constraint is `recovery_ceiling_exceeded` naming the niggle; so is a `pin_load`
above one.

### RPE ceilings

Every set under a cap (the return band's, the deload policy's `rpe_cap` in a light week, illness,
a niggle's `rpe_cap`) has
its load limited to `load_for(e1RM, fewest allowed reps, cap)` rounded down (the model and its
limits, rn:autoregulation.5 and .6). A set whose implied reps to failure would exceed 12 has its
reps cut to fit the model. With no usable e1RM the load
is clipped to the anchor's top load and the line warns `rpe_ceiling_unchecked`, quoting the
load as the rack step leaves it.

### The test set

In a `light_week`, when the version's deload policy has `test_priority_lifts`, a priority lift
under `top_backoff` or `wave_531` is prescribed one `test` single at `load_for(e1RM, 1, 9)`
rounded down (RPE 9 is opinion), before its working groups under the light cut. No test single
is prescribed on a line a return band or the illness RPE cap binds; the step records which
(`cause = return_band` or `illness`). This is the only `test` set there is: `test` is never authored (`set_type_not_allowed`, `program.md`), so a weekly max attempt is a
`working` single. The rule writes nothing from the result; the agent reads it at the block
boundary and records a `training_max` Decision if the lift moves to `wave_531`.

### Warm-ups

Step 8 derives each `warm_up` group's target as a percentage of the line's first working set's
load after step 7 (the `top_backoff` top, the first wave load, a pinned load), from the registry
ramp: one warm-up 60 %; two 50, 75; three 40, 60, 80; four or more spread evenly from 40 to 80.
Reps are the group's own. Each target then takes the ADR 0008 ladder: the row with the fewest
plates per side from 10 % under the target up to it, never above, ties lighter, then the row
whose plates contain the previous warm-up's. The ramp is this framework's heuristic, cited to no
source, and lives in the registry without an `rn:`.

## No last week

| Situation | The rule reads | Refuses or warns |
| --- | --- | --- |
| A line with no exposure of its exercise anywhere | `start_load` and the scheme's opening position | `start_load_missing` (violation) without one |
| A swap (`swap_exercise`) | the other exercise's own history (anchor rule steps 1–3), else the override's `start_load` | `start_load_missing`; never an e1RM borrowed from a substitute |
| An `amend` version | nothing changes: session ids and exercises carry their history | |
| A `redesign` with new session ids | anchor rule step 2: the exercise's newest exposure in any session | `start_load_ignored` at adopt where both exist and differ |
| A scheme change on a line | the new scheme's read of the same history (a `linear` line moving to `double_progression` starts from the anchor load at the bottom of the range) | |
| `top_backoff` with no e1RM in 42 days and no carried e1RM | the anchor's top load, held | `no_e1rm` |
| `wave_531` with no `training_max` Decision | `start_load` as the training max | `training_max_unused` is the reverse case |
| A layoff with no pre-layoff anchor in the session | anchor rule steps 2–3, then the band | |
| An exposure logged at 0 (or with no load) on a line in a rack mode | the next older exposure, else `start_load` (anchor rule, the skip); the band, if any, measures from that | `anchor_load_unusable`; `start_load_missing` without either |

## What the agent is handed

Per line, in the `plan draft` envelope and the `plan apply --dry-run` envelope:

| Field | Content |
| --- | --- |
| `prescription` | the set groups with loads (athlete units and Hevy kg), reps or range, RPE |
| `derived_from` | `exposure:<workout>/<exercise>` or `start_load` |
| `steps` | the derivation steps, in pipeline order, only those that changed something or found a ceiling not binding |
| `flags` | the line's violations and warnings, `validation.md`'s shape |
| `change` | one string, `4×6–8 @8: 120 → 125`, `held`, `first prescription`, `reset 120 → 107.5`; a `top_backoff` top the e1RM moved adds the e1RM and its exposure's date and session, `1×5 @8 + 4×5: 117.5 → 120 (e1RM 150 from 2026-10-13, pt-chest-back)`, whatever the later steps did to the load (the session is left out for a workout that matched none) |

No prose rationale. The `plan-week` skill judges only lines carrying a flag or an override and
shows the rest; its coaching questions are `skills.md`'s. `unexplained_drift` is the
validator's: `plan apply --dry-run` may read the previous WeekPlan's frozen prescription to
compare; `prescribe` never does.

## Worked examples from version 1

Home rack rows are plate-pool's; the barbell row above 120 is 125 and the row below 108 is
107.5 in these examples.

**Squat, `double_progression`, 4×6–8 @8, anchor 120.** Logged 8, 8, 8, 8 at RPE 7.5, 8, 8, 8:
every set at the top of the range at or under 8. Steps: `scheme 120 → 125 (hit)`, `rack 125
(row)`, `warm_up 60, 90` (ramp 62.5 and 93.75, laddered). Change `4×6–8 @8: 120 → 125`. Logged 8, 8, 7, 6 instead: under, hold at
120, no flag. Logged 8, 8, 8, 8 with the last at RPE 10: over, hold, `rep_range_missed`.

**Bench, `linear`, 4×5 @8, anchor 120.** Week 1 logged 5, 5, 5, 4: one miss, hold at 120.
Week 2 logged 5, 5, 4, 3: second consecutive miss at 120, reset to 0.9 × 120 = 108, rounded down
to 107.5. Steps: `scheme 120 → 107.5 (reset, misses 2)`. Change `reset 120 → 107.5`. The miss
count restarts when an exposure at 107.5 is logged; a second reset within two blocks is
`cadence_slow` at the boundary.

**Assisted pull-up, `assistance_ladder`, rungs 60…0, working group 4×8 @8, on rung 40, after 25 days off.**
Band 22–42: two rungs back to 60, sets 4 → 3, RPE ≤ 8. Steps: `cut rung 40 → 60 (return
22–42, 25 days off)`, `cut sets 4 → 3`, `rpe_ceiling 8`. Change `4×8 @8 rung 40 → 3×8 @≤8 rung
60`. The week after derives from this exposure: a hit at 60 moves to 50, not back to 40.

## Handed to other tickets

- **Schema** (#29, #42): the Niggle constraint field shapes and the scope CHECKs above; nothing
  else, since no derived value is stored (ADR 0003). The derivation steps are frozen with the
  prescriptions at approval.
- **Migration**: the old `linear` state (`misses`, `through`) is not migrated; the count derives
  from the imported exposures.
