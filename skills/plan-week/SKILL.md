---
name: plan-week
description: The week's prescription. Use when a check-in has closed a week, when a light or
  constrained week is agreed, or when a midweek change is needed, such as a session moved,
  dropped or added, a line swapped, a place away from home. Also /plan-week.
---

## Read first
The profile, once. The plan Draft from `coach plan draft` with its flags: each line carries its
prescription, the steps that derived it and its change from last week. Judge the lines that
carry a flag or an override; show the rest as they stand. The summary lists each flag code
with its count and keys; to read one code's flags with their messages, run
`coach query flags --draft <path> --code <code>`, or `--full` for every flag.

## Ask
State the week for confirmation: the rotation position, the day each session falls on, where
each is trained, and any light, minimum or one-off week already agreed. Ask only what the Draft
cannot know: a day lost, a trip, a lift that hurts today. One message; follow up only for a gap
that blocks the plan.

## Judge
Every answer is an override with its reason, an override Decision, or an Acknowledgement with
its reason. A load the engine derived is never retyped.
- **Stalls.** `stall_streak` wants `hold`, `restate_sets` or `swap_exercise`, chosen by the
  emphasis. Under hypertrophy, read dose against target: a flat line early in a block wants sets,
  late it wants the deload. On a priority lift, read the e1RM trend, not the week; a flat block
  is normal, not a crisis, and a new scheme is the program version's question, not this week's.
- **Rungs.** `rung_met`: the ladder's standing rung met its criterion and the next is offered.
  Ask the athlete; on their yes record a `ladder_rung` Decision naming the next rung with
  `because = "progress"`, or acknowledge the warning with the reason to hold. `ladder_top`: the
  last rung is met; acknowledge it and take the line's next step to the program version.
- **Missed reps.** `rep_range_missed`: the sets fell short of the range or ran past the RPE.
  Hold the load and look again next week, or restate the sets when the athlete says the range is
  wrong for them now.
- **Dose.** `dose_under_target`: a muscle has run under its target. Find the misses behind it
  before adding sets; then restate the sets on a line that trains it. `lift_dose_under_target`
  is the same for a priority lift, its counted variants included: restate the sets on the lift
  or on a variant it counts. `session_dose_high`: one session carries too much; move a line's
  sets to a lighter day or drop a line, the accessories first, never the priority lifts.
- **Fatigue.** When the check-in proposed a light week, take it as a `light_week` override,
  restating its cut or RPE cap with a reason where the triggers say so, or decline it with a
  `decline_ceiling` Decision and the reason. `light_week_shape_off_trigger` and
  `light_week_unprompted` name where the week departs from the proposal: acknowledge with the
  reason or change the week. A watch is a note for next week, not a lighter one. On a priority
  lift, read fatigue against its RPE cap; under maintenance, nothing weekly matters beyond the
  recovery ceilings.
- **Sessions.** `session_drop_suggested` names its reason: a status span, or a stack of hard
  work on one day. Answer with `drop_session` or `move_session`, the optional sessions first.
  A constrained week is a `minimum_week` that keeps what matters; a session somewhere else is
  `relocate_session`, a week away a `one_off_week`.
- **Persisting overrides.** `override_persisting` has three answers and none happens on its own:
  promote the override into a new program version, extend it with an override Decision and an
  until date, or leave it with an Acknowledgement and meet it again next week. Promote what the
  athlete will keep doing; extend what has an end in sight.
- **Rack.** `frozen_load_off_rack`: a load in the plan in force is gone from the location's
  rack. Say which planned loads move and to what, each load from the Draft.
- **Drift.** `routine_drift`: the athlete changed a routine in Hevy. Keep the change with the
  athlete's reason, or let this week's plan replace it; ask them which, in those words, when
  the reason is not plain.

## Explain
What the week is for in one sentence, then each session as the athlete will live it. Explain a
changed line by its emphasis: under hypertrophy, last week's reps at the authored RPE from the
steps; on a priority lift, the e1RM and what the scheme makes of it; under maintenance, held.
Every load and change comes from the Draft or the dry run; never retype one. Say each change
and its reason in plain words. Lines with no flag and no override are shown, not explained.

Run the verb's dry run and tell the athlete what it will record, every load quoted from it and
nothing of the system named; they say yes before the verb records it.

## Verbs
`coach status`, `coach plan draft`, `coach plan apply`, `coach query`, `coach record`
