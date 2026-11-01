# Cutover: history import and the fresh start

Spec for wayfinder #30, #31 and #32, decided 2026-10-31. The Hevy history comes across whole; the program does
not. Version 1 is designed from scratch through `onboard` and `program`, with the old routines
and the imported history as reference the agent reads. This replaces the pre-charting note that
the old program would carry over as version 1 (`program.md`'s worked example stays as an
illustration of the form). The ledger Draft of carried-over coaching state is "The cutover
check-in" below; the routines in Hevy and the week-boundary switch are "The switch".

## What carries and what does not

| Old fact | Target |
| --- | --- |
| Every Hevy workout the account still has (66 as of 2026-10-23, since 2026-03-29; every one a lifting workout with sets, 16 of them on a custom template) | `workout` and `logged_set` rows through `init`'s pull, full because no import has run |
| Hevy body measurements (42) | `weigh_in` rows, source `hevy`, through the same pull |
| Hevy routines and folders (17 and 4) | the `routine` and `folder` mirror through the same pull; none reaches `routine_map` ("The switch") |
| Custom Hevy template ids (11 in the account, 8 in the history) | `exercise.hevy_template_id`, through one plain `record` of ten `[[exercise]]` rows before `onboard` ("The exercise record") |
| Goal and Phase | the `goal adopt` Draft the `onboard` skill writes (`goals.md`) |
| Open niggles, open follow-ups, the patterns among the Coach's notes | the cutover check-in (below) |
| Two unlogged coach-led sessions (6 and 13 Oct 2026) | two manual `workout` rows in the cutover check-in: source `manual`, no session, title `PT session`, minutes, session RPE where reported, no sets. The third external annotation (20 Oct) is in Hevy and arrives with `import` |
| The `[cardio]` run caps | one `activity_cap` Decision in the cutover check-in |
| The 24 old Decisions | nothing. Every one expired by 2026-11-01 and names a session that will not exist |
| The `[caps]` table | nothing. The bar's limit derives from kit (ADR 0008) |
| The `[equipment]` table and plate-pool's committed `inventory/inventory.json` | `kit/home.json`, a copy of the inventory, and `kit/home.achievable.json` from one run of the generator; the PT's gym as a grid `[location.gym]`; both written by the `kit` skill (ADR 0021) |
| Resolved niggles, the two illness episodes, the resolved follow-up | nothing. They stay readable in the archived `data/` |
| Setup facts and history among the Coach's notes | nothing |
| The program, its 13 session ids, the rotation position, the Block count | nothing. Version 1 is a `redesign` and opens its own Block (ADR 0015) |
| 11 miss tags | nothing. They name planned sessions that never exist in the store |
| Load modes set per span by overlays (14 exercise rows) | nothing. Load mode is a column of the Exercise |
| Workouts deleted in Hevy before cutover | nothing. The old mirror dropped them, so no source remains for a tombstone |

## History import

- The first pull is `init`'s, full with `since` NULL because no import has run (`verbs.md`, "The
  pull"). It pages the whole account and stores every workout with its raw payload. The old `.coach/cache/hevy/` is never read: Hevy is the
  only source of its own history.
- No old session id becomes a `session` row. `workout.routine_id` stays as inert text (it has no
  foreign key); 29 of the 66 old workouts carry none, and three of the fifteen routine ids it
  names were retired or temporary routines.
- Pre-cutover workouts have no Match. Match derives from a planned session's window
  (`week.md`), and no WeekPlan covers those weeks. A routine id is only a tiebreaker inside that
  window, so there is no second Match rule keyed on routine ids.
- The imported history still anchors the fresh program: the anchor exposure reads "same session,
  any session, `start_load`" (`prescription.md`), so every exercise the athlete has logged
  anchors on its history and `start_load` is only required for exercises never logged.

## Exercise resolution on read

A logged set's Exercise is derived, not stored. `logged_set` carries `hevy_template_id` and
`hevy_title`; Exposure resolution joins `hevy_template_id` to `exercise.hevy_template_id` (unique)
when it reads. Consequences:

- The pull does not depend on the library being seeded, so it runs before the program exists.
- A mapping recorded later heals every workout version at once with no re-import.
- `exercise_unmapped` is a view over logged sets whose template id no Exercise carries, one flag
  per workout. It clears when an `[[exercise]]` record maps or declares the Exercise.

Three writers set `exercise.hevy_template_id`:

| Writer | When |
| --- | --- |
| the catalogue seed at `init` | Hevy built-in template ids (eight hex characters, the same in every account) shipped with the catalogue entry (`src/coach/store/catalogue.jsonl`, `schema.md` "The engine catalogue"); seeded from the old library's 108 catalogue pairs and the six that the old code resolved by title |
| an `[[exercise]]` record | an account-specific custom template: an edit to an existing Exercise, or a new Exercise with every column and `source = record` when no program line names it |
| `plan apply` | after a verified `POST /v1/exercise_templates` (ADR 0011) |

Import maps by template id only. There is no title heuristic. Expected `exercise_unmapped`
after the first pull is one flag per workout that carries a custom template (16 of 66 as of
2026-10-23), and 0 of 66 once the exercise record of step 3 is taken; the denominator on the day
is the workout count `init`'s `pull` reports. It is checked by eye on the day (`testing.md`, "The
cutover Draft").

## Order of store writes at cutover

1. `coach init --hevy-key <key>`, which ends with the full pull: the whole history, the routine
   and folder mirror, body measurements. `status` now shows the unmapped template list. If Hevy
   is unreachable, `init` exits 4 with the instance written, and the next pulling verb runs the
   full pull.
2. The `kit` skill: `kit/home.json` copied from plate-pool's inventory, the generator run once,
   `[location.home]` and the grid `[location.gym]` written (ADR 0021).
3. `coach record` of the exercise record: the ten custom templates as library Exercises ("The
   exercise record"). `exercise_unmapped` drops to 0 and every later Draft can name their ids.
4. The `onboard` skill: profile, Goal and Phase (`goal adopt`), no program. A priority lift on
   the Goal names an exercise id, so the library must already hold it.
5. The `program` skill: version 1 designed fresh and adopted (`coach program adopt`). The agent
   reads the old routines from the mirror and the imported history as reference and takes a
   critical view of both. Its lines on the ten custom templates reference library ids and declare
   nothing, so the Draft carries no template columns for them and the dry run later shows zero
   templates to create.
6. `coach checkin record` of the cutover check-in: open niggles with their constraints, open
   follow-ups, Observations, the run cap, the two manual PT workouts.
7. The first `plan draft` and `plan apply`: fresh routines, nothing adopted ("The switch").

The pull comes before design because it is read-only against Hevy and the design should see the
history it will anchor on. The exercise record comes before `onboard` because the Goal's
priority lifts and the niggle constraints of step 6 name exercise ids, and `program adopt` would
otherwise demand the four create columns for exercises whose template already exists.

## The exercise record

A plain `record` file (`verbs.md`, the `exercise` record kind), not part of the check-in: it
carries no Observation and confirms nothing about a date. One `[[exercise]]` row per custom
template the old library knows, as a new library Exercise with `source = record`, keeping the old
id. A new Exercise declares every library column (`name`, `load_mode`, `equipment_kind`,
`pattern`, `muscles`; `schema.md`) plus `hevy_template_id` and `hevy_title`; the other three
Hevy columns (`hevy_exercise_type`, `hevy_equipment`, `hevy_muscle_group`) are the create
columns, and an Exercise whose template exists never needs them (`validation.md`,
`hevy_template_missing`). A template the account holds and the library never knew waits for
`exercise_unmapped` to name it.

Content as of 2026-10-31: ten rows, `custom_arch_hold`, `custom_decline_lateral_raise`,
`custom_dip_negatives`, `custom_flexed_arm_hang`, `custom_hollow_hold`, `custom_jumping_pull_up`,
`custom_pallof_press_band`, `custom_pull_up_top_hold`, `custom_straight_arm_lat_pulldown_band`,
`custom_suitcase_carry` (eight in the history, in 16 of the 66 workouts). If version 1 later
declares one of them again, adopt's upsert edits the row field by field and `hevy_template_id`
stays (`program.md`, "New exercises").

## The cutover check-in

The carried-over coaching state is one Draft, hand-written by the agent at cutover from the
archived `data/` and `profile.md`, reviewed line by line by the athlete, and taken by
`checkin record`. No converter script and no hidden verb: the Draft is about a dozen tables, and
this section pins their content so the agent at cutover only brings niggle status up to the day.

It is a check-in file, not a plain `record` file, because Observations are reserved to the
check-in (ADR 0009) and every carried row should name the check-in that confirmed it. The row is
ordinary: tier `deep`, window the old instance's final week (the file sets `window_start`, which
the engine accepts on the instance's first row only, `week.md`), read "state carried from the
old instance" in the coach's words. It is the instance's first deep check-in on record, so the deep
cadence and `defer_deep_review` count from cutover day. `checkin open` is not run first; nothing
in the schema marks it special.

| Kind | Rule | Content as of 2026-10-31 |
| --- | --- | --- |
| `[[niggle]]` | open niggles only, one record each: `opened` = old `first_noted`, `site`, the current status (old `watching` is `reported`), the old history collapsed into the event text, and the constraint set the agent proposes from the old prose and the overrides that cite the niggle, each confirmed or struck by the athlete in the file. Resolved niggles and the illness episodes do not migrate | two: hamstring after runs (n-0003, easing, proposed `rpe_cap` 7 on pattern `hinge`); left shoulder (n-0006, easing, proposed `rpe_cap` 7 on `db_lateral_raise` if still in force) |
| `[[follow_up]]` | open follow-ups only, one `kept` event each, `due` = old `review_at` | none |
| `[[observation]]` | the Coach's notes that are patterns with evidence (ADR 0009). Agreements about how to coach stay in `profile.md`; agreements that shaped the old program inform the fresh design and become no record; setup facts and history are dropped | seven: drift adds volume; drift adds intensity on top sets; PT sessions run hard whatever is asked; PT sessions go under-logged; the PT's A/B alternation is unreliable; active holidays are training stress; the PT rarely programmes deadlifts |
| `[[decision]]` | one `activity_cap` for runs with the old `[cardio]` numbers, because `pain`, evidence `niggle:@hamstring` (the `[[niggle]]` record in the same file carries `key = "hamstring"`; the engine rewrites the ref to the assigned id, `verbs.md`), no `until`, retired when the hamstring resolves. `park_session` rows only if version 1 authors the conditioning sessions and the athlete still wants them parked | `activity_kind = "run"`, `weekly_distance = 17`, `single_distance = 6` |
| `[[workout]]` | the external PT annotations whose session Hevy never saw, minutes and RPE as reported, NULL where not | two: 6 Oct 2026 (60 min, RPE unknown), 13 Oct 2026 (60 min, RPE 9) |

The Draft lives at `.coach/drafts/<date>-checkin.toml` (`instance.md`), gitignored; the export
`publish` commits is the record, and the Draft hash on every row is the audit.

### Acceptance check

The expected `coach status` after step 6 is the check; every item is a field of its default
summary (`verbs.md`), read with `--fields`:

- `exercise_unmapped`: 0 of 66 workouts (0 of whatever count the import reported);
- two open niggles, each with at least one constraint (no "niggle open with no load constraint"
  warning);
- open follow-ups: none, or exactly the ones the Draft carried;
- the seven Observations current;
- two manual workouts;
- one `activity_cap` in force;
- one current Goal and one open Phase;
- `publish --dry-run` row counts equal to the Draft's table counts.

During the last old week the athlete runs this Draft once by hand against a scratch instance and
checks this list by eye; the suite exercises the same path with a synthetic Draft
(`testing.md`). The real Draft is never an engine test. The former check, "the first `plan apply --dry-run` reproduces the
old instance's next week", compared programs; with the program not carried there is none to
compare.

## The switch

### Routines

The account holds 17 routines in four folders (Week A, Week B, Conditioning, One-off weeks) and
one with no folder. No old routine is adopted: the fresh design has no session that maps to one,
and ADR 0011's spare rule takes only routines already in the Routine map. The first `plan apply`
POSTs one routine per planned session of the week (ADR 0011: a push projects the WeekPlan's
sessions, so a rotation session first planned in a later week gets its routine on that week's
push) and creates the folders those routines need: Program, and Standing when the week plans a
standing, daily or rehab session; Retired is created by the first retire. No old folder carries
those titles, so adoption by title finds nothing. Routines the account holds that no Routine map row names, at cutover or later, sit in
the `routine` mirror and are never flagged, retired or touched; `query routines` shows the map,
not the mirror. The athlete deletes the old routines and folders by hand in the app, and only
after the first push has verified: while they coexist they cost nothing, and they are the
rollback. Their mirror rows stay after the deletion; import never deletes a mirror row
(ADR 0011).

### Order

Everything except the push happens during the last old-instance week, in the new instance repo,
while the old instance keeps serving: steps 1 to 6 above, then `plan apply --dry-run` for the
coming Monday until it passes clean. None of these writes Hevy. Sunday evening, after the last
old-instance session is logged:

1. `coach import`: the event pull by hand, since `plan apply` reads the frozen WeekPlan and does
   not pull; Sunday's workout arrives.
2. `plan apply --dry-run`; the pre-push checklist below holds.
3. `plan apply --expect <hash>`.
4. `publish`.
5. The athlete deletes the 17 old routines and the four old folders in the app.
6. The old instance repo gets a plain commit of its state as it stands and both old repos are
   archived on GitHub (read-only, reversible). The old instance runs no final check-in: the
   cutover check-in's window is its last week.

### Pre-push checklist

Every item is a number the engine already prints:

- the engine is a release, `coach status` shows its version equal to the pin with no
  `engine_pin_dev`, and the test suite is green at that tag (an editable `.dev` install is for
  development; `init` refuses to pin one, `verbs.md`);
- `coach status` shows the acceptance list of "The cutover check-in";
- the hand pull reports Sunday's workout (`workouts.new` of one);
- the dry run shows routine creates equal to the WeekPlan's planned session count, one folder
  create per folder those routines need (Program, and Standing when one is a standing, daily or
  rehab session), zero updates, zero retires, zero templates to create, no violation, and its
  hash is the one passed to `--expect`;
- `plan apply --dry-run --full` shows no line anchored on a workout from the old instance's last
  deload week. Pre-cutover workouts have no Match, so `prescription.md`'s rule that skips
  light-week logs cannot see them, and an old deload log can be the first anchor. Where one is,
  the agent writes a `pin_load` override on the line with the reason and the dry run is re-run.

### Rollback

No path touches Hevy workout history. A refusal before any PUT (exit 3, exit 4) sent nothing. A
POST that verifies badly leaves an `unverified` map row and a re-run resumes it (ADR 0006, 0011).
If the re-run fails too, the athlete trains the week from the old routines still in the app, the
old instance is not yet archived and serves the week, and the new instance's approved WeekPlan is
superseded by the next Monday's `plan draft`.

## Known gaps, stated once

- Adherence reads "insufficient" for the first four ordinary weeks after cutover: no planned
  session exists before the first WeekPlan.
- Workouts deleted in Hevy before cutover have no tombstone.
- The anchor rule cannot tell an old deload-week log from a hard-week log (no Match before the
  first WeekPlan); the pre-push checklist catches it once, and from the second WeekPlan on every
  anchor is matched.
- The old `linear` miss state, the Block count and the rotation position do not carry; the
  fresh version resets all three by construction.
