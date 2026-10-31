---
status: accepted
date: 2026-10-26
amended: 2026-10-31 by wayfinder #39 (the return band is a safety bound with no override route; its fact, days off, moves only through a `trained_unlogged` Annotation or a hand-entered Workout)
---

# The rule derives every line; the agent departs from it only through typed, reasoned overrides

Code derives each prescription from the program version, the exposures and the WeekPlan's
overrides (ADR 0003). The agent never writes a number into a line and never chooses among
per-line candidates. Its judgement enters as typed overrides, scoped to the week, a planned
session or a line, each carrying a kind, a reason and the evidence it rests on. A validator
reports every violation and warning per line in one envelope, and refuses approval while any
hard violation stands anywhere in the plan. There is no bypass: to go against a hard constraint
the agent changes the fact behind it (closes a niggle, declines a block ceiling, records a
training max) through a verb that leaves a dated Decision, then re-derives.

## Considered options

- **Rule derives, agent overrides by type (chosen).** Matches how coaches work (wayfinder #14):
  the scheme moves the dose weekly, departures are few and named. The agent's surface stays small
  and every departure is a countable fact.
- **Code emits candidates per line, agent picks one.** The review's first sketch. Makes the agent
  touch every line of every plan, and the chosen number has no typed cause behind it.
- **Code applies a fixed policy, agent files exceptions in prose.** The old `propose_line`:
  twelve layers of policy with English rationale, overrides regex-policed. The policy caps the
  coaching at the code's heuristics, and prose carried loads.

## What is hard and what is a warning

Hard (approval refused):

- A load off the kit grid for the exercise, location and load mode.
- A load or RPE above a recovery ceiling: a niggle's load cap or no-added-load constraint, the
  return band's cut from the pre-layoff exposure, the illness RPE 7 cap on the first session
  back, a light week's RPE cap.
- A return line whose band, load, set delta and RPE cap do not all agree with the days off.
- A hard-week count over the block ceiling with no Decision declining the ceiling.
- A line whose exercise has no Hevy template id or whose load mode disagrees with the exercise.
- An approval naming a WeekPlan that is not the current draft, or whose rotation position is
  unconfirmed.

Warnings (reported, never blocking): a top set above the e1RM model at the target RPE, or no
e1RM; an increment larger than the scheme's step; a historical off-grid load ignored as an
anchor; evidence flags (over the rep cap, short-sleep week, stall streak, follow-up due, niggle
open with no constraint); drift from last week's prescription with no override explaining it.

## Override shape

- Scopes: week, planned session, line. Nothing finer: a change to one set is a line kind that
  restates the line's set groups.
- Reason: a kind, a `because` category (pain, kit, stall, fatigue, schedule, athlete request,
  coach judgement), free text in the coach's voice, and optional evidence references (niggle,
  exposure, check-in). No regex or word-count policing of the text.
- A load appears in an override only as the typed Load on a `pin load` kind, which still passes
  the grid and ceiling checks. Prose never carries a load.
- The override catalogue (wayfinder #19) lists the kinds per scope.

## Consequences

- The return cut (template #257) is prevented by signature, not by a branch or a stored anchor:
  `prescribe` reads exposures and overrides and has no access to any WeekPlan, so re-proposing,
  rebuilding or re-planning midweek a 43+ line recomputes the same cut from the same pre-layoff
  exposure. Regression test: propose, approve, rebuild, re-plan midweek; the load is unchanged.
- The 43+ "re-test" is not a rule. The week after a return week derives from the return
  exposure by the ordinary scheme.
- A session with no prescribed working set is excluded from the hard-week gate: it neither
  passes nor fails and does not make a week count as hard.
- The validator has no override switch, so every departure from a safety bound is traceable to
  a Decision.
- The return band is a safety bound like a niggle's cap: no override waives or softens it, and
  `pin_load` lowers only. Its fact is days off per lift, which a `trained_unlogged` Annotation or
  a hand-entered Workout moves by recording training that happened (amended 2026-10-31,
  `docs/spec/prescription.md`).
- Each hard constraint is downstream of a record the agent can change through a verb, which is
  a test on the verb set (wayfinder #16): no constraint may exist without such a verb.
