# Weekly prescription: how last week's exposures move this week's dose

Spec for wayfinder #26, decided 2026-10-31. The decision behind the pipeline is ADR 0017; the
pure function and the freeze at approval are ADR 0003; the hard and warning line is ADR 0005;
the schemes that exist are `program.md`'s; the override kinds are `overrides.md`'s; the
rounding and the ladder are ADR 0008's. Flag codes raised here are rows in `validation.md`.
Nouns are in `GLOSSARY.md`.

The shape in one paragraph: for every line of every planned session, `prescribe` picks one
**anchor exposure**, lets the line's scheme move the dose from it, applies the plan's line
override and any override Decision in force, applies **one** week-kind transform, then the
niggle constraints, the RPE ceilings, the safety ceiling and the rack, and finally derives the
warm-ups. Each step is recorded as a **derivation step** (step, from, to, cause), so the agent
reads why a line landed where it did instead of a prose rationale. The rule never writes a
number the agent did not ask for: it holds and warns where the old engine guessed.

## The anchor exposure

Per line, in this order:

1. The newest Exposure of the line's exercise **in the same session id**, skipping any
   exposure matched to a planned session in a `light_week` (deload logs are never a baseline).
   A return-week exposure is kept: the return week's logs are the baseline for the week after
   (ADR 0005: no 43+ re-test rule).
2. If none in the last 90 days: the newest exposure of the exercise in **any** session (a
   redesign with new session ids, a swap, a new line of an exercise already trained).
3. If none: the line's `start_load` (or the `swap_exercise` override's) and the scheme's
   opening position (`program.md`, the scheme table). A load-bearing line with neither is
   `start_load_missing`.

e1RM is always exercise-wide: the best qualifying point in the 42 days before the planned date,
every session included. A newer exposure with more than 12 reps to failure at or above that
point's load invalidates it until a newer qualifying point exists.

**The anchor's load.** The anchor's top working load, as logged. A logged load that is not a row
of the session location's rack is replaced by the nearest row **at or below** it, and the line
warns `offgrid_anchor_ignored` naming both. A historical load never defines the grid.

**Days off per lift** = `max(layoff, exposure age − usual interval)`, where the layoff is the
gap since the last lifting exposure of any kind (coach-led counts), the usual interval is the
median of the lift's last four gaps clamped to 7–14 days, and 10 days of grace apply before a
lift counts as decayed. `no_training` status spans count as days off.

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
week transform.

| Scheme | Reads from the anchor | Hit | Move on a hit | Under | Over |
| --- | --- | --- | --- | --- | --- |
| `double_progression` | reps and RPE per working set | every working set reached the top of its range at or under the authored RPE | load to the next rack row; reps back to the bottom of the range | hold load and range | a set at RPE ≥ authored + 2, or below the bottom of the range: hold and warn `rep_range_missed`. The rule never cuts |
| `linear` | reps per working set at the anchor load | every working set at the authored reps at or under the authored RPE | load to the next rack row | a short attempted set is a **miss**: hold. A set never logged is incomplete, not a miss | see **Stalls**: the second consecutive miss at one load resets |
| `hold` | nothing | | the authored sets at the anchor load (`start_load` with no anchor) | | |
| `assistance_ladder` | reps and RPE per set on the current rung | every set at `reps` at or under `rpe` | one rung up (less assistance); hold at the last rung | hold the rung | hold the rung and warn `rep_range_missed` on a set at RPE ≥ `rpe` + 2 |
| `top_backoff` | the exercise's best e1RM in the window | not a hit test: the top load is `load_for(e1RM, top.reps, top.rpe)` rounded down, **capped at one rack row above the anchor's top load**; back-offs are `pct_of_top` of the top, rounded nearest | | no e1RM in the window: hold the anchor's top load and warn `no_e1rm` | a top set logged above the model raises the e1RM; nothing else |
| `wave_531` | the current `training_max` Decision (`start_load` until one exists), the Block's hard-week count and the last rep-out | the wave is `hard weeks completed in the block mod 3`; loads are the wave's percentages of the training max rounded down; the last working set is open | | a rep-out below its wave's reps: warn `rep_range_missed` | after the third wave is logged at one training max: warn `training_max_due` with the three rep-out counts. The rule **never** moves the training max; the agent records a `training_max` Decision (+2.5/5 kg, or −10 %) |

Notes:

- The one-row cap on `top_backoff` is a rule, not a warning: a bigger jump is the model
  over-reading one great day. Because every scheme's own step is at most one row,
  `increment_over_step` fires only on a `pin_load` more than one row above the anchor.
- `top_backoff` reads the **best** point in the window, so one bad day never drops the top set;
  only a recovery ceiling or the window expiring lowers it.
- With no next rack row (a band at the top of its ladder, a dumbbell rack's heaviest pair) a
  hit holds and the step records `cause = rack_top`; the agent swaps or the version changes.
- A `test` single (`program.md`) is prescribed only in a deload week, below.
- A `hold` override replaces the scheme's move only: the week transform, constraints and
  ceilings still apply to a held line.
- Conditioning sessions carry a session scheme and read the last matched Activity:
  `emom_density` at or under `rpe_target` → `minutes + minutes_step` up to `minutes_cap`, then
  one rep per exercise up to `reps_cap`; over target → hold. `circuit_rounds` → one round up to
  `rounds_cap`, then reps. No Activity → the params as authored. Their lines run `hold`.

## Stalls

One definition: three consecutive ordinary exposures of the line (light-week and return-week
exposures skipped) with no gain on the scheme's metric raise `stall_streak` with the three
exposure refs. The metric per scheme:

| Scheme | Metric | The rule's own response |
| --- | --- | --- |
| `double_progression` | total reps at or under the authored RPE at the anchor load | none: hold. Sets, a deload or a swap are the agent's (`goals.md`, the cadence table at the boundary) |
| `linear` | a miss | the **reset**: the second consecutive miss at one load (`misses_before_reset = 2`) sets the load to `reset_factor = 0.9` × the anchor load, rounded **down** to the rack. The miss count restarts once an exposure at a lighter load is logged. Resets per lift are derived from history; `cadence_slow` reads them |
| `assistance_ladder` | the rung | hold the rung |
| `top_backoff` | e1RM | none: the model holds the top set |
| `wave_531` | the rep-out count | none: `training_max_due` or `rep_range_missed` says what happened |

A stall is a warning the agent judges within the block; the scheme may change only at the block
boundary (`goals.md`, **Response to a cadence signal**). RPE rising at a held load on many lines
is fatigue, not a stall, and is the deload policy's.

## The pipeline

ADR 0017. Each step runs once, in this order, and records `(step, from, to, cause)` on the line
when it changed anything. No step may raise a load a previous step lowered.

| # | Step | Reads | Does |
| --- | --- | --- | --- |
| 1 | `scheme` | the anchor, the version's line | the move above |
| 2 | `override` | the plan's line override | `swap_exercise` re-runs step 1 on the other exercise; `pin_load` replaces the working load (grid and ceilings still apply); `hold` repeats the anchor's dose; `restate_sets` replaces the set groups; `drop_line` ends the line |
| 3 | `decision` | override Decisions in force on the planned date | the same kinds; the plan's override wins on the same kind and line |
| 4 | `week` | the week kind | exactly one of: the return band, the deload cut, the light cut, nothing (below) |
| 5 | `niggle` | open Niggles | constraints, strictest binds (below) |
| 6 | `rpe_ceiling` | the week kind, illness, niggle caps | every capped set's load limited through the e1RM model (below) |
| 7 | `rack` | the location's rack, a `safety_ceiling` Decision | the safety ceiling truncates the rack; the load rounds to a row (ADR 0008: nearest by direction; a cut rounds to the nearest row no heavier than its target) |
| 8 | `warm_up` | the working load | the ADR 0008 ladder (fewest plates within −10 % of target) |

Ceilings never compose: a load cap from a niggle, a safety ceiling, an illness RPE cap, the
light week's RPE ceiling and a `pin_load` all bind by `min`. A step that found a stricter
ceiling already binding records `cause = not_binding`.

### Week kind

Derived inside `prescribe` from the plan's week override, the status spans and the days off,
in one precedence order; the first that holds names the week:

| Order | Kind | Holds when | Transform on every lifting line |
| --- | --- | --- | --- |
| 1 | `break` | a `no_training` span covers the whole week | no session is planned |
| 2 | `light` | a `light_week` override | type `deload`: two-thirds of each working group's sets (rounded, min 1), loads −10 % from the anchor, every set RPE 6, rep-outs closed. Type `light`: two-thirds of the sets, loads held, RPE ≤ 8 |
| 3 | `minimum` | a `minimum_week` override | the kept sessions derive as normal; the rest are dropped |
| 4 | `one_off` | a `one_off_week` override | every session at the named location; otherwise as normal |
| 5 | `return` | days off for the lift > 10 | the return band, below |
| 6 | `illness` | an `ill` span since the line's anchor and no exposure since it ended | no cut; RPE 7 on every set of the line (step 6) |
| 7 | `hard` | otherwise | none |

The closed week's kind for the Block's count (light, return, break, minimum, one_off, hard,
missed, partial) is `week.md`'s read after the fact; this table is the prescribing read.
`return` and `illness` are per line here (days off and illness are per lift); the others are per
week. `week.md`'s `return` is the athlete's whole-week layoff, and illness is no closed-week
kind at all.

### The return band

Days off per lift as above. The cut is measured from the **lower** of the scheme's proposal and
the anchor's load, so a return week never carries a progression, and from the pre-layoff
anchor only: the week after derives from the return-week exposure by the ordinary scheme.

| Days off | Load | Working sets | RPE cap |
| --- | --- | --- | --- |
| 0–10 | none | none | none |
| 11–21 | ×0.95 | −1 (min 1) | ≤ 8 |
| 22–42 | ×0.90 | −1 | ≤ 8 |
| 43+ | ×0.85 | −1 | ≤ 7 |

Per scheme: `assistance_ladder` steps back 0/1/2/3 rungs by band instead of a load cut, and
assistance is never cut; `wave_531` multiplies the training max by the band factor for the
return week only, with no rep-out set. A return line whose band, load, set delta and RPE cap do
not all derive together (an override fought the band) is `return_band_disagrees`.

Illness alone (gap ≤ 10 days) is not a cut: the RPE 7 cap is the whole return. Illness with
days off > 10 is a return week with the cap at 7.

### Niggle constraints

Four kinds on the Niggle record (`niggle_constraint` rows per event, `schema.md`), binding while the
niggle's status says so (ADR 0010); the strictest across every open niggle binds:

| Kind | Does |
| --- | --- |
| `rpe_cap` | caps every set's RPE; a load limit follows in step 6 |
| `load_cap` | caps the working load, athlete units |
| `no_added_load` | caps the working load at the anchor's top load; a floor on assistance |
| `avoid` | an exercise id or a movement pattern: the line is dropped by derivation |

A line over a constraint is `recovery_ceiling_exceeded` naming the niggle; so is a `pin_load`
above one.

### RPE ceilings

Every set under a cap (the return band's, the light week's, illness, a niggle's `rpe_cap`) has
its load limited to `load_for(e1RM, fewest allowed reps, cap)` rounded down. A set whose implied
reps to failure would exceed 12 has its reps cut to fit the model. With no usable e1RM the load
is clipped to the anchor's top load and the line warns `rpe_ceiling_unchecked`.

### The test set

In a `light_week` of type `deload`, when the version's deload policy has `test_priority_lifts`,
a priority lift under `top_backoff` or `wave_531` is prescribed one `test` single at
`load_for(e1RM, 1, 9)` rounded down, before its working groups under the deload cut. The rule
writes nothing from the result; the agent reads it at the block boundary and records a
`training_max` Decision if the lift moves to `wave_531`.

## No last week

| Situation | The rule reads | Refuses or warns |
| --- | --- | --- |
| A line with no exposure of its exercise anywhere | `start_load` and the scheme's opening position | `start_load_missing` (violation) without one |
| A swap (`swap_exercise`) | the other exercise's own history (anchor rule steps 1–3), else the override's `start_load` | `start_load_missing`; never an e1RM borrowed from a substitute |
| An `amend` version | nothing changes: session ids and exercises carry their history | |
| A `redesign` with new session ids | anchor rule step 2: the exercise's newest exposure in any session | `start_load_ignored` at adopt where both exist and differ |
| A scheme change on a line | the new scheme's read of the same history (a `linear` line moving to `double_progression` starts from the anchor load at the bottom of the range) | |
| `top_backoff` with no e1RM in 42 days | the anchor's top load, held | `no_e1rm` |
| `wave_531` with no `training_max` Decision | `start_load` as the training max | `training_max_unused` is the reverse case |
| A layoff with no pre-layoff anchor in the session | anchor rule steps 2–3, then the band | |

## What the agent is handed

Per line, in the `plan draft` envelope and the `plan apply --dry-run` envelope:

| Field | Content |
| --- | --- |
| `prescription` | the set groups with loads (athlete units and Hevy kg), reps or range, RPE |
| `derived_from` | `exposure:<workout>/<exercise>` or `start_load` |
| `steps` | the derivation steps, in pipeline order, only those that changed something or found a ceiling not binding |
| `flags` | the line's violations and warnings, `validation.md`'s shape |
| `change` | one string, `4×6–8 @8: 120 → 125`, `held`, `first prescription`, `reset 120 → 107.5` |

No prose rationale. The `plan-week` skill judges only lines carrying a flag or an override and
shows the rest; its coaching questions are `skills.md`'s. `unexplained_drift` is the
validator's: `plan apply --dry-run` may read the previous WeekPlan's frozen prescription to
compare; `prescribe` never does.

## Worked examples from version 1

Home rack rows are plate-pool's; the barbell row above 120 is 125 and the row below 108 is
107.5 in these examples.

**Squat, `double_progression`, 4×6–8 @8, anchor 120.** Logged 8, 8, 8, 8 at RPE 7.5, 8, 8, 8:
every set at the top of the range at or under 8. Steps: `scheme 120 → 125 (hit)`, `rack 125
(row)`, `warm_up 60, 95`. Change `4×6–8 @8: 120 → 125`. Logged 8, 8, 7, 6 instead: under, hold at
120, no flag. Logged 8, 8, 8, 8 with the last at RPE 10: over, hold, `rep_range_missed`.

**Bench, `linear`, 4×5 @8, anchor 120.** Week 1 logged 5, 5, 5, 4: one miss, hold at 120.
Week 2 logged 5, 5, 4, 3: second consecutive miss at 120, reset to 0.9 × 120 = 108, rounded down
to 107.5. Steps: `scheme 120 → 107.5 (reset, misses 2)`. Change `reset 120 → 107.5`. The miss
count restarts when an exposure at 107.5 is logged; a second reset within two blocks is
`cadence_slow` at the boundary.

**Assisted pull-up, `assistance_ladder`, rungs 60…0, 4×8 @8, on rung 40, after 25 days off.**
Band 22–42: two rungs back to 60, sets 4 → 3, RPE ≤ 8. Steps: `week rung 40 → 60 (return
22–42, 25 days off)`, `week sets 4 → 3`, `rpe_ceiling 8`. Change `4×8 @8 rung 40 → 3×8 @≤8 rung
60`. The week after derives from this exposure: a hit at 60 moves to 50, not back to 40.

## Handed to other tickets

- **Schema** (#29): the Niggle constraint field shapes; nothing else, since no derived value
  is stored (ADR 0003). The derivation steps are frozen with the prescriptions at approval.
- **Migration**: the old `linear` state (`misses`, `through`) is not migrated; the count derives
  from the imported exposures.
