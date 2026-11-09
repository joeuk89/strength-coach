---
status: accepted
date: 2026-11-08
amended: 2026-11-09 by the owner on the review of PR #305 (exposures count from the day after a `ladder_rung` Decision's date, and from the adoption date itself on the first rung, for the load, the criterion and `stall_streak` alike)
---

# Rungs may share an exercise, the rung's start tells the stages apart, and a later rung may carry its own start load

A rung of an `exercise_ladder` is an exercise, or a harder way of performing the same
exercise, with its cues and one working group. Two rungs may name one exercise when they
differ in `sets` or `cues`; what tells their histories apart is the standing rung's start
(the `ladder_rung` Decision's date, or adoption for the first rung), which the criterion and
`stall_streak` already read from. A load-bearing rung after the first carries its own
`start_load`, checked at adopt. Tempo stays prose in the rung's cues. Issue #290; amends the
rejected option of ADR 0023.

## Context

The athlete's program climbs three ladders whose rungs are one exercise performed harder:
pull-up and dip negatives lowered for longer once every set reaches its reps, and a balance
hold lengthened by 10 s once both holds are clean. ADR 0023 rejected rungs that share an
exercise because "Hevy logs the exercise id, so two stances under one id are one history",
and asked for a custom exercise per stance. The athlete rejected that workaround: it splits
one movement's history across several exercises to record a change in how it is performed.
The objection no longer describes the engine. Since #256 the criterion and `stall_streak`
read only exposures of the standing rung's exercise from the rung's start, so a rung is
already told apart by when it began, not by its id.

## Considered options

- **Rungs may share an exercise, differing in sets or cues (chosen).** Every ladder rule,
  Decision, flag and page stands; `duplicate_id` counts each distinct rung exercise once per
  session; a rung identical to its predecessor in exercise, sets and cues is `rung_repeated`.
- **A new scheme for same-exercise stages.** Rejected: it repeats the climb rule for one
  difference in the rung table.
- **One custom exercise per stage.** Rejected by the athlete; it also puts the engine's
  bookkeeping into the athlete's exercise library.
- **A `tempo` key on the rung.** Rejected: the engine cannot read tempo from a log or send it
  to Hevy, so a key is a cue with extra ceremony. A tempo rung's criterion is its reps at
  RPE, and the athlete's yes to `rung_met` carries the word that the tempo was held, where
  the yes already lives (ADR 0023).
- **A hold-length generator (`duration_step`, `duration_cap`).** Rejected: the ladder is
  declared whole and readable in the version (ADR 0015); the generator saves three lines.
- **A `load_mode` key on the rung for a weighted step.** Rejected: load mode is the
  exercise's property. The vest rung is a load-bearing exercise carrying `start_load`.

## Consequences

- The glossary's Rung widens to "an exercise, or a harder way of performing the same
  exercise"; "stage" stays on its avoid list.
- `duplicate_id` reads the set of a line's rung exercises, not the list. The adopt errors
  gain `rung_repeated` (line scope: a rung equal to the one before it in exercise, sets and
  cues; only neighbours are compared, so a ladder may return to an earlier shape later).
- A `[[rungs]]` table after the first may state `start_load`. A load-bearing rung without
  one is `start_load_missing` at adopt, not plan time; `start_load` on a rung whose exercise
  is not load-bearing, or on the first rung (whose start load is the line's), is an adopt
  error. The rung's exercise decides whether it is load-bearing, as a line's does.
- Every surface names a rung by index and dose, with its exercise only when it changes from
  the standing rung: `rung_met`'s params, the Hevy note's "Next:", the check-in card, the
  approval prompt, the routine page, the progress page and `program show`.
- History matching, the return band, the light week and the `rung_met` / `ladder_top`
  hashes are unchanged: they keyed on the rung index and the rung's start already.
- Exposures count on a rung from the day after a `ladder_rung` Decision's date, for the load,
  the criterion and `stall_streak` alike, so the workout that earned a climb is never the new
  rung's first exposure. The accepted cost: a session trained on the new rung on the Decision's
  own date does not count. A first rung's start is adoption, which no earlier rung earned, so
  its exposures count from the adoption date itself, in `coach progress` and the cadence signals
  as in `plan draft`.
