---
status: accepted
date: 2026-10-26
---

# v1 is training only: nutrition, recipes and meal plans leave the engine

The rebuilt engine covers the training loop and the facts it reads. Nutrition (app readings,
protein floor, calorie estimate, the dated override rule, `/goals`), recipes and meal plans are
out of the engine and out of this spec. Three facts the training loop needs survive as their own
records: the weigh-in, the sleep night and the activity. Research notes stay, as authored files
cited only from code.

## Considered options

- **Training only (chosen).** The old system's purpose is weekly training planning; the athlete
  uses MacroFactor, which owns every calorie and protein number, and the override rule was never
  used. Meal plans were never used in their final form. Dropping them removes about 5k lines of
  code and tests and three config tables before the schema is designed.
- **Port nutrition as its own module.** The review's sketch kept `nutrition` and `recipes` as
  modules. Rejected: nothing in the training loop reads them, and the one rule that crossed over
  (the dieting sleep gate) belongs to the nutrition decision, not to fatigue.
- **Keep a separate small recipe tool.** Rejected for now: the 40 cards stay readable in the
  archived instance repo, and a tool would be built for a workflow nobody runs.

## Consequences

- Weigh-in, Sleep night and Activity are core tables, entered by hand or derived from Hevy. No
  Apple Health or Health Auto Export importer in v1: it was disabled and no run data ever arrived.
- The activity rules that stay are the concurrent-training spacing rules, the run-spike review and
  the two-quality-bouts cap. Cardio identity matching, associations, HR fields and the session-RPE
  load ladder go.
- The Short-sleep week trigger stays and reads sleep nights; with no importer it fires only on
  typed-in nights. The nutrition Sleep gate goes.
- Research notes are parsed at runtime, never imported; every threshold in code carries its `rn:`
  ref and one test resolves every ref to a current claim. No citation scan of prose, no rendered
  regions, no prose tests.
- Nothing in v1 is optional, so there are no feature toggles.
- The nutrition phase is a line in the prose Profile; the dose-target rule reads only the lifting
  goal.
- Bringing nutrition or recipes back is a fresh effort with its own map.
