---
status: accepted
date: 2026-11-07
---

# A ladder is a scheme whose rungs may be exercises, the standing rung is a Decision, and the engine offers the climb but never takes it

Work with no load to add (bodyweight, skill and practice lines) progresses by a ladder: an
ordered run of rungs, each an exercise with its cues, one working group and an advance
criterion the engine reads from the logs. The ladder is declared whole on the line as its
scheme (`exercise_ladder`, beside `assistance_ladder` whose rungs are loads). The rung the
line stands on is a `ladder_rung` Decision, opening at the first rung when none exists. When
the standing rung's criterion holds, `plan draft` raises `rung_met` naming the next rung and
the check-in card lists it; the agent records the Decision after the athlete's yes or
acknowledges the warning with a reason. Nothing climbs on its own. Spec: `docs/spec/program.md`,
`prescription.md`, `overrides.md`, `check-in.md`; issue #256.

## Context

A loaded lift's progression is its scheme and, at a block boundary, the switching table
(ADR 0017, `goals.md`). A pull-up negative, a band pull-up or a balance-board stance has no
load to move: the next step is a different exercise or a harder stance, and the engine had no
place for that run of steps. Ladders lived in a line's `cues` string, one rung at a time, and
the athlete had to remember to report a change. The research note
`bodyweight-skill-progression` already frames skill work as a ladder climbed one rung on a hit.

## Considered options

- **A ladder scheme of exercise rungs, the standing rung a Decision (chosen).** One Ladder
  concept with two scheme rows (loads, exercises) and one climb rule. The version stays whole
  and the ladder stays readable in it (ADR 0015); the position is a recorded choice with a
  reason, as a training max is (ADR 0003, 0016); the engine's part is the criterion and the
  warning, the human's part is the yes.
- **A `stage` field stored on the line.** Rejected: stored progression state (ADR 0003), and a
  version that must be re-adopted to move one rung.
- **Each advance as a program `amend`.** Rejected: the ladder's later rungs leave the record,
  the version history fills with one-line changes, and a step back after a layoff needs another
  amend.
- **The engine advances when the criterion holds.** Rejected: a rung change is a coaching
  choice with a reason, and a stance the logs cannot tell apart (eyes closed, one foot) needs
  the athlete's word.
- **A ladder on any line, loaded lifts included.** Rejected: a loaded lift already has a ladder
  of schemes driven by cadence signals; a second record would duplicate it.
- **Rungs that share an exercise and differ by cues only.** Rejected: Hevy logs the exercise id,
  so two stances under one id are one history; a stance that must be told apart is its own
  custom exercise and `manual` is kept for the rare rung that cannot be.

## Consequences

- The glossary's Practice loses "nothing to progress" and keeps optional and unjudged; Rung
  widens to an exercise rung; Ladder and Advance criterion are entries.
- A line's `exercise` is its first rung's exercise and stays the line's key for every scope
  (overrides, flags, `override_persisting`, one exercise per session) for the life of the
  version; history matching reads the standing rung's exercise.
- The criterion and `stall_streak` read exposures from the standing rung's start: the Decision's
  date, or adoption for rung 1. The return band steps back by rungs and a light week holds the
  rung, as `assistance_ladder` does. `rung_met` and `ladder_top` hash on the rung only, so one
  acknowledgement or `leave_warning` holds until the rung moves.
- The reason enum gains `progress`. The Decision catalogue gains `ladder_rung`; the flag
  registry gains `rung_met`, `ladder_top`, `rung_exercise_unknown`, `ladder_too_short` and
  `advance_criterion_off_rung`; the switching table gains an `exercise_ladder` row.
- The Hevy routine carries the standing rung only, with the next rung named in that exercise's
  note; the routine page, `program show` and the progress page show the whole ladder with the
  standing rung marked.
