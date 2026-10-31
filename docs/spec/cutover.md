# Cutover: history import and the fresh start

Spec for wayfinder #30, decided 2026-10-31. The Hevy history comes across whole; the program does
not. Version 1 is designed from scratch through `onboard` and `program`, with the old routines
and the imported history as reference the agent reads. This replaces the pre-charting note that
the old program would carry over as version 1 (`program.md`'s worked example stays as an
illustration of the form). The routine steps in Hevy and the hour-by-hour switch belong to the
routine cutover ticket; the ledger Draft of carried-over coaching state belongs to the migration
ticket. This file settles what each of them may assume.

## What carries and what does not

| Old fact | Target |
| --- | --- |
| Every Hevy workout the account still has (66 as of 2026-10-23, since 2026-03-29) | `workout` and `logged_set` rows through the ordinary `import --full` |
| Hevy body measurements (42) | `weigh_in` rows, source `hevy`, through the same pull |
| Hevy routines and folders (17 and 4) | the `routine` and `folder` mirror through the same pull; `routine_map` is the routine ticket's |
| Custom Hevy template ids (11 in the account, 8 in the history) | `exercise.hevy_template_id`, recorded by `[[exercise]]` at onboarding |
| Open niggles, follow-ups, observations, Goal, Phase | the ledger Draft (migration ticket) |
| Three external PT sessions | three manual `workout` rows in the ledger Draft: source `manual`, no session, title `PT session`, minutes, session RPE, no sets |
| The program, its 13 session ids, the rotation position, the Block count | nothing. Version 1 is a `redesign` and opens its own Block (ADR 0015) |
| 11 miss tags | nothing. They name planned sessions that never exist in the store |
| Load modes set per span by overlays (14 exercise rows) | nothing. Load mode is a column of the Exercise |
| Workouts deleted in Hevy before cutover | nothing. The old mirror dropped them, so no source remains for a tombstone |

## History import

- The first import is `import --full` with `since` NULL. It pages the whole account and stores
  every workout with its raw payload. The old `.coach/cache/hevy/` is never read: Hevy is the
  only source of its own history.
- No old session id becomes a `session` row. `workout.routine_id` stays as inert text (it has no
  foreign key); 29 of the 66 old workouts carry none, and three of the fifteen routine ids it
  names were retired or temporary routines.
- Pre-cutover workouts have no Match. Match derives from a planned session, and no WeekPlan
  covers those weeks. There is no second Match rule keyed on routine ids.
- The imported history still anchors the fresh program: the anchor exposure reads "same session,
  any session, `start_load`" (`prescription.md`), so every exercise the athlete has logged
  anchors on its history and `start_load` is only required for exercises never logged.

## Exercise resolution on read

A logged set's Exercise is derived, not stored. `logged_set` carries `hevy_template_id` and
`hevy_title`; Exposure resolution joins `hevy_template_id` to `exercise.hevy_template_id` (unique)
when it reads. Consequences:

- `import` does not depend on the library being seeded, so it runs before the program exists.
- A mapping recorded later heals every workout version at once with no re-import.
- `exercise_unmapped` is a view over logged sets whose template id no Exercise carries, one flag
  per workout. It clears when an `[[exercise]]` record maps or declares the Exercise.

Three writers set `exercise.hevy_template_id`:

| Writer | When |
| --- | --- |
| the catalogue seed at `init` | Hevy built-in template ids (eight hex characters, the same in every account) shipped with the catalogue entry; seeded from the old library's 108 catalogue pairs and the six that the old code resolved by title |
| an `[[exercise]]` record | an account-specific custom template: an edit to an existing Exercise, or a new Exercise with every column and `source = record` when no program line names it |
| `plan apply` | after a verified `POST /v1/exercise_templates` (ADR 0011) |

Import maps by template id only. There is no title heuristic. Expected `exercise_unmapped` on
the first pull is 0 of 57 once the eight custom templates in the history are recorded; the parity
harness asserts it on the fixture.

## Order of store writes at cutover

1. `coach init`.
2. `coach import --full`: the whole history, the routine and folder mirror, body measurements.
   `status` now shows the unmapped template list.
3. The `onboard` skill: profile, Goal (`goal adopt`), and version 1 designed fresh. The agent
   reads the old routines from the mirror and the imported history as reference and takes a
   critical view of both.
4. `coach program adopt` of version 1.
5. `coach record` of the ledger Draft: the custom template ids, niggles, follow-ups,
   observations, Phase, the three manual PT workouts.
6. The first `plan draft` and `plan apply`. What happens to the 17 old routines in Hevy at that
   push is the routine ticket's decision. The athlete may delete old routines by hand in the app
   beforehand; the hard constraint covers workout history, not routines.

Import comes before design because it is read-only against Hevy and the design should see the
history it will anchor on.

## Known gaps, stated once

- Adherence reads "insufficient" for the first four ordinary weeks after cutover: no planned
  session exists before the first WeekPlan.
- Workouts deleted in Hevy before cutover have no tombstone.
- The old `linear` miss state, the Block count and the rotation position do not carry; the
  fresh version resets all three by construction.
