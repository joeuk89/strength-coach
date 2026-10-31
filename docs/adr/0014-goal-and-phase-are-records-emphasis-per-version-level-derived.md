---
status: accepted
date: 2026-10-27
amended: 2026-10-31 by wayfinder #41 (adopt fills `[dose]`, `[deload]` and session `minutes` only; scheme, RPE and rest are authored on every line by the `program` skill and adopt warns when they sit outside the emphasis band; cadence signals are defined per scheme); 2026-10-31 by wayfinder #46 (`checkin open` reads the Phase; two violations and seven warnings at adopt)
---

# The Goal and the Phase are records, each Program version carries an emphasis, and training level is a derived per-lift signal

The athlete's goal is a ledger record with one current row: a kind (`hypertrophy` or
`strength`), an ordered list of priority lifts, typed milestones with no date, and the why in
words. Each Program version carries an `emphasis` (`hypertrophy`, `strength`, `maintenance`)
chosen from the goal; at adoption the version's dose and deload are filled from the emphasis when
unsaid and written into the version, so the weekly rule reads the version and never the goal
(amended: scheme, RPE and rest are authored per line and only checked against the emphasis). The
body-composition phase (`deficit`, `maintenance`, `surplus`, with a rate and an until condition)
is its own record, opened and closed with a reason. Training level is not stored anywhere: code
derives per-lift cadence signals from resets and e1RM trend and raises them as warnings at the
block boundary, and a graduation is a new Program version with a Decision citing the signal.
Code reads the goal at two moments, adopt and the block boundary, and the phase there and at
every `checkin open` (trend and until condition); the coach reads them at every judgement through
a derived progress report. Spec: `docs/spec/goals.md`.

## Context

ADR 0009 put a `goal` field on the Program version with one effect, the default dose target,
and left how goals reach the agent and the other formulas open. In the old instance the goal
never reached the loop (`dose_intent` was null). The athlete's brief for this decision: the goal
must shape the long-term direction, the program and every weekly prescription, detect when the
athlete has moved up a level, and never be a bootstrapping step that is then forgotten. Two
research notes were written first: `docs/spec/goal-programming.md` (what each goal changes in
a program, with evidence) and `docs/spec/training-level.md` (how coaches define level and plan
long term).

## Considered options

- **Goal record plus emphasis per version (chosen).** A goal outlives program versions, so it
  needs its own row; a block optimises one thing, so the version names it. The version carries
  the filled defaults explicitly, keeping `prescribe` blind to the goal and each rule in one
  place (ADR 0005, 0013).
- **Goal only on the Program version (ADR 0009 as written).** Rejected: nothing then spans
  versions, so no progress against the goal, no milestones, no "this block serves that aim".
- **Goal in the profile prose only.** Rejected: documents are output, never input, so code could
  raise nothing from it and the goal would again stop at onboarding.
- **A fourth goal kind, `strength_and_hypertrophy`.** Rejected on the evidence: strength is
  load-specific and hypertrophy is not, mixing loads across a week costs nothing, and every
  powerbuilding default (strength scheme and test on some lifts, those lifts first, per-lift
  dose, what the check-in asks first) is carried by the priority lifts. "Strong and jacked" is
  a hypertrophy goal with priority lifts.
- **`maintenance` as a goal kind.** Rejected: maintenance keeps a goal's schemes and intensity
  and cuts sets, so it has no schemes of its own to supply; it is an emphasis a block runs.
- **A typed Strategy of ordered future blocks with exit conditions.** Rejected: no coach source
  keeps one, the evidence for sequencing blocks by quality is weak, and the only long-range
  structure that changes what a week is checked against is the body-composition phase. The
  long-term direction stays in prose; the next block is judged at each boundary from the
  progress report.
- **Training level as a stored fact (`[athlete].experience`) or an athlete-wide `set level`
  Decision.** Rejected: every coach defines level by rate of progress on a lift, years barely
  predict that rate, and level is per lift in every source. A stored label would be read by a
  formula nothing supports. `experience` leaves `coach.toml`.
- **Undated milestones as prose (ADR 0009).** Rejected now: a typed target lets code compute
  distance and date reached from e1RM and weigh-ins, which is what makes progress visible.

## Consequences

- New records: Goal (immutable rows, one `current`), Milestone (on the Goal), Phase (one open).
  `goal adopt` is a plain store write from a Draft; the Phase is opened and closed inside a
  `checkin record` or `goal adopt` draft; no `phase` verb, no `level` anywhere in code.
- Program version: `goal` becomes `emphasis`; `priority_lifts` come from the Goal; adopt fills
  `[dose]` and `[deload]` from the emphasis when unsaid and shows them in the diff (amended
  2026-10-31: scheme, RPE and rest are authored on every line by the `program` skill, which
  proposes them from `goals.md`'s bands; adopt fills none of them and warns
  `scheme_off_emphasis` when a scheme sits outside the band). A `strength` version must have priority
  lifts. Two violations (`goal_missing`, `priority_lifts_required`) and seven warnings at adopt
  (`docs/spec/goals.md`, Adopt: the goal checks).
- The weekly rule is unchanged in signature; goal-specific weekly behaviour is a property of
  the scheme the version names.
- `coach progress` is a read verb (block summary per priority lift, milestones, dose, adherence,
  phase), rendered to `pages/progress.md`; the `program` skill reads it at the block boundary
  and a deep check-in reads it too.
- Cadence signals `cadence_slow` and `cadence_fast` per exercise at the block boundary, with
  cited, opinion-marked thresholds, each condition stated per scheme (amended 2026-10-31); `phase_condition_met` and `phase_trend_off` join the
  registry (a milestone reached is a `progress` figure, not a code, amended 2026-10-31,
  `docs/spec/week.md`); scope kinds `version` and `exercise` are added.
- ADR 0009 is amended: the version field is `emphasis`, `experience` leaves `[athlete]`,
  milestones are typed on the Goal. `GLOSSARY.md` replaces Lifting goal with Emphasis and adds
  Goal, Priority lift, Milestone, Phase and Cadence signal.
- Program authoring (#22) and Weekly prescription (#26) take the defaults table and the stall
  and reset definitions respectively; the Verb set (#16) takes `goal adopt` and `progress`.
