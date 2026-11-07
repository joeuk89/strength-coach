---
name: program
description: Authoring or revising a program version. Use for the first program once the
  profile and Goal exist, at a block boundary, after a cadence signal or a sustained stall,
  when a swap has persisted, when a parked session is promoted, or when the athlete's days,
  kit or fixed sessions change. Also /program.
---

## Read first
The profile, once. For a revision, the progress report from `coach progress` and the current
version from `coach program show --draft`. For a first program, the imported history and any
routines in the mirror, read as what the athlete has done, never as what they should do next.
Before proposing a new exercise, check the library with `coach query exercises`.

## Ask
State for confirmation what is already known: the days and minutes, each location and its kit,
and every session the athlete does not control (coach-led, a sport, a class) with its day and
what it trains. Ask only what is missing: the lifts they want to feel first, exercises they
refuse or love, and for a revision what the last block taught them that the numbers cannot
show. One message; follow up only for a gap that blocks the design.

## Judge
- **The split.** Fit the week to the days the athlete has, never the reverse. Each muscle
  twice across a rotation week where the days allow, once with a reason where they do not. A
  fixed session covers what it covers, its estimated sets count, and the designed sessions fill
  around it: never the same muscles hard the day after. Fewer sessions done beats more sessions
  missed; under `low` adherence design the smaller week with the same hard sets per muscle.
- **Coverage.** Every pattern in the rotation. The hinge and a carry go in on purpose because
  they are dropped first; `muscle_no_hard_sets` sees a muscle, not a pattern.
- **Order and time.** Priority lifts first (`priority_lift_not_first`), the heaviest work while
  fresh, accessories last and the first cut when `session_over_minutes` fires. Read each
  session's estimate against its `minutes` in the dry run; cut accessories first where it runs
  close. Superset small lifts to buy time, never the compounds.
- **Scheme, RPE and rest per line.** A top set and back-offs on a load-bearing priority lift,
  double progression elsewhere, a ladder while a lift is assisted. A coarse rack, a new lift or
  a technique lift stays on reps. `scheme_off_emphasis` marks each departure; acknowledge it
  with the reason or change the line.
- **Dose.** The filled targets open a block, they do not cap it. Raise a muscle the report shows
  behind and under target; leave what is growing alone. A deficit keeps the dose, a surplus can
  carry more; `dose_off_band` names the departure. An older athlete, or one who recovers slowly,
  earns the shorter block and the fuller deload, not a smaller dose.
- **Signals.** Answer `cadence_slow` and `cadence_fast` only with a move the flag lists, the
  Decision citing the flag. A stalled double-progression line wants sets, a swap or a new rep
  range, never a new scheme. RPE rising everywhere is fatigue for the deload policy; on one
  line it is technique or a niggle.
- **Emphasis and Phase.** The Goal's kind unless this block serves it better another way
  (`emphasis_off_goal`): maintenance when life asks for less, a strength block when a milestone
  is close. Re-read the Phase at every boundary against the trend the report shows and what the
  athlete says about their body; a new Phase travels in the Goal draft.
- **Kind.** A swap, a scheme change or a session changed inside the same split is an `amend`.
  A new split, emphasis or Phase is a `redesign`; one mid-block is acknowledged with why the
  block cannot finish (`block_open_at_redesign`).

## Explain
Walk the athlete through the week as they will live it, session by session, then the rules
that move it week to week. Say why each exercise is there and what would earn a swap. Every
load, set count and default comes from the adopt dry run; never retype one. For a revision,
lead with what changed over the block and what this program does about it.

Run the verb's dry run and tell the athlete what it will record, every load quoted from it and
nothing of the system named; they say yes before the verb records it.

## Verbs
`coach status`, `coach progress`, `coach program show`, `coach program adopt`,
`coach goal adopt`, `coach query`, `coach schema`
