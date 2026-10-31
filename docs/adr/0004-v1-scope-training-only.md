---
status: accepted
date: 2026-10-26
amended: 2026-10-31 by ADR 0014 (the Phase is a record that moves the dose default within its band, `goals.md`; the Profile line is gone)
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
- The activity rules that stay are three codes (`docs/spec/week.md`, amended 2026-10-31): the
  quality-bout cap `activity_cap_exceeded`, the run spike `run_spike`, and the concurrent-training
  spacing as `session_drop_suggested` with reason `quality_stack`. Cardio identity matching,
  associations, HR fields and the session-RPE load ladder go.
- The Short-sleep week trigger stays and reads sleep nights; with no importer it fires only on
  typed-in nights. The nutrition Sleep gate goes.
- Research notes live in the engine repo only, never imported into the store, never shipped as
  package data and never read by a running agent (ADR 0020); every threshold in code carries its
  `rn:` ref and one test in the repo resolves every ref to a current claim or a numbered section
  (`docs/spec/research-notes.md` lists the notes and the two ref forms). That test is a registry
  test in `tests/contract/`, the second of the two named exceptions to the no-prose rule in
  `docs/spec/testing.md`: it reads claim numbers and section headings, never a claim's text. No
  citation scan of prose, no rendered regions, no other prose tests. (Amended 2026-10-31: the
  original "parsed at runtime" meant this test.)
- Nothing in v1 is optional, so there are no feature toggles.
- The body-composition phase is a Phase record (deficit, maintenance, surplus, with a rate and an
  until condition) that moves the dose default within the emphasis band and sets the bodyweight
  trend the check-in reads; calories stay with the athlete's nutrition app. (Amended 2026-10-31:
  the original made it a line in the prose Profile read by no rule; ADR 0014 and `goals.md`.)
- Bringing nutrition or recipes back is a fresh effort with its own map.
