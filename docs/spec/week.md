# The closed week

What a week counted as once it has passed: its kind, the Block count it moves, the adherence it
feeds, the fatigue triggers it fired, when the check-in that closes it is due, and how a logged
workout is matched to a planned session in the first place. Every figure here is a view of the
store at a date, never stored (ADR 0018). The prescribing read of a week, the transform each
kind applies to a line before it is trained, is `prescription.md`'s; this document is the read
after the fact.

Decided on wayfinder ticket [The closed week](https://github.com/joeuk89/strength-coach/issues/38),
2026-10-31. Every threshold is an engine constant with its `rn:` citation beside it in code (ADR
0013); the citations here name the claim each constant is filled from.

## Match

The link from a workout to the planned session it fulfilled, or none.

A workout can match only a planned session whose **window** covers the workout's date:

| Cadence | Window |
| --- | --- |
| `weekly` | the planned date |
| `standing` | any day of the plan's week |
| `daily` | the day itself (each day is its own planned session) |

Among the planned sessions whose window covers the date, a workout whose `routine_id` equals the
session's routine takes that session first; otherwise it takes the first unmatched candidate in
session order. Each workout matches at most one planned session and each planned session takes
at most one workout, so two workouts on a day with one planned session leave the second
unmatched. A routine id is a hint inside the window, never a Match on its own: a workout logged
from a routine on a day no session's window covers is unmatched. Workouts are matched in date
order, then by Hevy start time.

A `match` Annotation naming the planned session overrides the rule for that workout (two
workouts on one day, a session logged on the wrong date). Pre-cutover workouts have no Match
because no WeekPlan covers them (`cutover.md`).

### What an unmatched workout is

A workout with no Match is classed by its content:

- **Conditioning** when every logged set sits on an Exercise whose load mode is `duration` or
  `distance`. It yields an Activity view (minutes from start and end, RPE from the log or 7,
  quality when the RPE is 7 or more, rn:running-load.6) and no Exposures.
- **Lifting** otherwise. It yields Exposures (history is history; the anchor rule in
  `prescription.md` reads "same session, any session") and nothing else: it counts for no
  planned session, so it enters neither the gate nor adherence until an `add_session` override or
  a `match` Annotation claims it.
- A workout whose templates no Exercise carries yields `exercise_unmapped` and nothing else.

A matched workout yields what ADR 0010 says its session kind yields.

## Session kinds in the week

Two tiers, two denominators:

- The **gate denominator** is the planned core `lifting` and `coach_led` sessions of the week.
  Conditioning, practice and rehab never make a week hard and never fail it (ADR 0010).
- The **adherence denominator** is the planned core sessions of every kind.

A planned session on a day inside a status span (`ill`, `injured`, `travel`, `no_training`) that
was **not** trained leaves both denominators: the athlete agreed not to train that day
(rn:deloads.13, read to include illness and injury). One trained anyway counts in numerator and
denominator alike. A `cancelled` Annotation removes the session from both denominators. A session
with zero prescribed working sets (every line `hold`, or none authored) is outside the gate
denominator and neither passes nor fails (ADR 0005); it stays in the adherence denominator.

A planned session is **trained** when it has a Match, a `trained_unlogged` Annotation, or is a
coach-led session that happened (a Match, or a hand-entered Workout with no sets). A shortened
session is trained. A Miss is a planned core session whose week has closed untrained, unmoved and
uncancelled.

## The session gate

A trained core lifting session **passes** when at least two-thirds of its prescribed working
sets were logged and the mean logged RPE is no more than 1.5 below the mean prescribed RPE; a set
with no RPE counts as on target. A coach-led session passes when it happened. A lifting session
added by `add_session` is in the gate denominator like any other. The gate counts training stress
for the fatigue count, not whether the prescription was met (rn:deloads.11). The
against-the-prescription read (reps missed, effort off by 1.5 or more, RPE missing) is a card
figure per session and never a gate.

## Week kind

The closed week's kind is derived once the week has passed, by one precedence order; the first
that holds names the week and sets what it does to the Block count. Fractions are over the gate
denominator after the exclusions above.

| Order | Kind | Holds when | Block count |
| --- | --- | --- | --- |
| 1 | `light` | the plan in force carried `light_week` | the Block closes; count 0 |
| 2 | `return` | the athlete's gap between their last lifting workout before the week's first lifting workout and that workout is over 10 days | the Block closes; count 0 |
| 3 | `break` | every planned core lifting and coach-led session was untrained on a status-span day, so the gate denominator is empty | paused |
| 4 | `minimum` | the plan carried `minimum_week` | paused |
| 5 | `one_off` | the plan carried `one_off_week` | paused |
| 6 | `hard` | at least 75 % of the gate denominator passed the gate | +1 |
| 7 | `missed` | under 50 % of the gate denominator was trained | the Block closes; count 0 |
| 8 | `partial` | otherwise: 50 to 75 % trained, or 75 % or more trained with under 75 % passing | paused |

Citations: 75 % and 50 % are rn:deloads.2; the paused kinds are rn:deloads.13; `return` is a
whole-week layoff, so a line in a return band while the athlete kept training other lifts does
not make the week `return`, and the 10-day edge is the first return band's (`prescription.md`).
A week with nothing planned at all is `partial`. `illness` is not a closed-week kind: an `ill`
span prorates the denominators like any span, and the per-line illness transform stays
`prescription.md`'s.

The **ordinary** kinds are `hard`, `partial` and `missed`: a week the program ran as authored,
however it went. The other five are disrupted weeks.

### The Block

The Block is a run of weeks under one hard-week ceiling (glossary). Its count is the number of
`hard` closed weeks since it opened. It opens at a `redesign` adoption or the week after a week
that closed it, and closes by a `light`, `return` or `missed` closed week or by a `redesign`
version (ADR 0015); paused weeks leave the count where it was. `wave_531` reads the count mod 3
(`prescription.md`); `block_ceiling_exceeded` reads it against the version's
`hard_weeks_ceiling` (`validation.md`); `cadence_slow` reads closed hard Blocks (`goals.md`).

## Adherence

Trained over the adherence denominator, summed across the last four **ordinary** closed weeks
inside the trailing eight calendar weeks. Fewer than four ordinary weeks in that lookback is
`insufficient`. The eight-week cap is the engine's opinion: adherence from before a month-long
break says nothing about the athlete now.

| State | Figure | Reader |
| --- | --- | --- |
| `ok` | 80 % or more | none |
| `watch` | under 80 % | `adopt`: a version adding a core session raises `core_session_added_low_adherence` (rn:deloads.7) |
| `low` | under 70 % | the `check-in` skill's Judge presents a smaller schedule with the same weekly hard sets per muscle (rn:deloads.6); no code |
| `insufficient` | fewer than four ordinary weeks | none |

Optional sessions never enter adherence; their done-count is a streak on the card.

## Fatigue triggers and the light-week proposal

Four triggers, read over the check-in's window:

| Trigger | Holds when | Source |
| --- | --- | --- |
| readiness | the check-in's `readiness` is `poor` | the Check-in row (`check-in.md`) |
| RPE drift | a compound lift's logged RPE was 1 or more over target on 2 or more working sets in each of two consecutive exposures, each set against its own prescription with none extra, heavier, longer or with more reps, after an earlier steady exposure at the prescription, outside deload, light and return work | rn:autoregulation.4 |
| niggle | a Niggle status event `aggravated` inside the window, or a niggle still `aggravated` on the window's first day | Niggle events |
| Short-sleep week | at least 4 of the last 7 measured nights under 7 hours, with at least 4 nights of data | Sleep nights (glossary) |

Two triggers in one window **propose** a light week; one is a **watch** (rn:deloads.5). Under 3
completed hard weeks nothing is proposed and the card says `skipped (<n> hard weeks)`
(rn:deloads.4). The count reaching the version's `hard_weeks_ceiling` proposes whatever else is
true (rn:deloads.3; `block_ceiling_exceeded` holds the plan to it).

The proposed **type**: the ceiling, RPE drift or a niggle choose `deload`; readiness or sleep
alone choose `light` (rn:deloads.8 to .10). The transforms are `prescription.md`'s. The coach
chooses the type on the plan with a reason; `light_week_type_off_trigger` and
`light_week_unprompted` judge the plan against this proposal (`overrides.md`).

A proposal **stands** until the next plan carries a `light_week` override or a `decline_ceiling`
Decision is written after it; `status` reports a standing one as "light week or deload pending".
Two triggers with no light week taken is the coach's call and raises nothing.

## Dose

Per muscle, the fractional hard sets delivered in the closed week (direct 1, indirect 0.5; a
hard set is a working set above RPE 5, rn:volume-frequency.2, rn:proximity-to-failure.5) against
the version's target, and the mean over the trailing four ordinary weeks. The card carries it;
`plan draft` raises `dose_under_target` when delivered dose is under target in at least three of
the trailing four ordinary weeks (rn:volume-frequency.3) and `session_dose_high` when a planned
session exceeds 11 fractional sets (rn:volume-frequency.1). `progress` keeps its block-boundary
view.

## Activity rules

Three rules, each a code; the rest of the old activity layer is gone (ADR 0004 amended).

| Rule | Code | Where |
| --- | --- | --- |
| Quality bouts (session RPE 7 or more) capped at 2 a week, runs and conditioning together | `activity_cap_exceeded` | outside a plan, history |
| A run over 1.10 times the longest run in the previous 30 days, judged only once 14 days of activity history exist before it | `run_spike` | outside a plan, history; clears when the week closes |
| A planned quality conditioning session within 24 hours before a planned heavy squat or hinge session (a working set at RPE 7 or above, or 6 reps or fewer with no RPE), or on the same day as any lifting session with under 6 hours between | `session_drop_suggested`, reason `quality_stack` | plan draft |

Citations: rn:running-load.5 and .6; rn:running-load.1 and .4; rn:concurrent-training.4 and .5.
Dropped: the warning on each conditioning session in a light week, the "sleep debt" reason (the
Short-sleep week trigger covers it) and the 43+ re-test (ADR 0005 already says it is not a rule).

## When a check-in is due

| Tier | Due when |
| --- | --- |
| light | today minus the newest `current` Check-in's `date` is at least `[athlete].checkin_cadence_days` (default 7). With no row, from the first approved WeekPlan's Monday plus the cadence minus one day |
| deep | 42 days since the newest `current` row with `tier = deep` (rn:deloads.12), or a light week newly proposed, or a `redesign` version adopted since that row, or the previous check-in was a catch-up; suppressed by a `defer_deep_review` Decision until its date |

A **catch-up** is a check-in whose window is longer than 10 days; its deep tier is deferred to
the next check-in by the same test. `checkin open --tier deep` is honoured on a catch-up, since
the flag only raises the tier.

The first Check-in's `window_start` is the first approved WeekPlan's Monday, or the `date` itself
with no plan; the record file may set `window_start` on the first row only, which is how the
cutover check-in names the old instance's final week (`cutover.md`). Every later window starts
the day after the previous `current` row's `window_end`.

A week is **closed** when a `current` Check-in's window covers its Sunday.

## Which verb reports which outside-plan code

| Verb | Codes |
| --- | --- |
| `checkin open` | `phase_trend_off`, `phase_condition_met`, `followup_due`, `niggle_unconstrained`, `cadence_slow`, `cadence_fast`, `training_max_unused`, `activity_cap_exceeded`, `run_spike` |
| `import` | `routine_drift`, `workout_reappeared`, `exercise_unmapped`, `snapshot_stale` |
| `status` | `engine_pin_dev`, and every code standing |
| `plan draft` | any of the above that bears on a line (`validation.md`) |
