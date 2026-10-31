---
status: accepted
date: 2026-10-27
amended: 2026-10-31 by wayfinder #42 (a reappearing workout id gets a `back` presence row and reads again under a warning; import upserts the routine and folder mirrors and never deletes a row; Hevy set types map to `warm_up` or `working`); 2026-10-31 by wayfinder #43 (the refusals name their exit class and code); 2026-10-31 by wayfinder #44 (the Write audit is written by the client behind the `HevyClient` protocol, two lines per request; one test double, `FakeHevy`, and the real client tested with a recording opener; the 429 retry below the protocol)
---

# Hevy is a projection target: allow-listed writes, append-only import, retire not delete

The engine talks to Hevy through one client with a hard allow-list of four write endpoints and a
read-only view of everything else. Workouts come in append-only as versions with tombstones;
routines go out as projections of the plan in force, verified by read-back, with every request
recorded in a committed audit file. Hevy's API (swagger fetched 2026-10-27) has no DELETE on any
path and no PUT on folders, so nothing in the account is ever removed: a routine is retired and
reused, a folder is forever.

## Considered options

- **Allow-list of four endpoints, workout POST excluded (chosen).** No verb writes a workout; a
  manual log is a local Workout row. The hook's rule stays "any method on `/v1/workouts*` is
  denied" with no exception.
- **Allow workout POST for test workouts.** Permitted by the hard constraint, needed by nothing.
- **Delete retired routines.** Impossible: the API has no DELETE. ADR 0010 is amended.
- **A folder per program.** Folders cannot be renamed or deleted, so each program would leave a
  dead folder in the app.
- **A raw-JSON cache directory beside the store (the old `data/hevy/`).** A second source of truth
  with its own freshness checks.

## The client

- Allow-list: `POST /v1/routines`, `PUT /v1/routines/{id}`, `POST /v1/routine_folders`,
  `POST /v1/exercise_templates`. Any other non-GET raises before a request is built. Permission
  config denies every method on `/v1/workouts*` and `WebFetch` to the Hevy host (ADR 0006).
- API key from the environment, else `.env`; header only; scrubbed from errors, envelopes and
  audit lines. 429: sleep 30 s, three tries, inside the client and below the `HevyClient`
  protocol (ADR 0019), so nothing above it sleeps; a token bucket on writes; reads never
  throttled. One test double, `FakeHevy`, which satisfies the protocol and nothing more, bumps
  `updated_at`, drops routine-level notes on PUT and can corrupt a read-back (`testing.md`). The
  real client is tested with a recording opener that refuses every connection (amended
  2026-10-31: the earlier "fixture transport" was this, not a second double).

## Import

- One verb pulls workouts (events since the last import minus a 10-minute overlap; `--full`
  re-lists everything), routines, folders, exercise templates and body measurements, and stores
  normalised rows with the raw payload kept on the row. No cache directory. Exposure, Match, e1RM
  and the Activity of a conditioning workout stay views; the `activity` table holds hand-entered bouts only (ADR 0018).
- A Workout is versioned by (Hevy id, `updated_at`). An app edit appends a version; reads take the
  latest. A delete event, or an id missing from a full pull, appends a `gone` tombstone row (id,
  noticed at, source `event` or `full`). Reads skip a workout whose latest tombstone row is
  `gone`; the rows stay; a tombstone row is never withdrawn. An id that reappears gets a `back`
  tombstone row and a `workout_reappeared` warning, not an undo (amended 2026-10-31): its latest
  version reads again from that moment, and the warning clears by a `match` or `void`
  annotation on it. Hevy's set type `warmup` lands as `warm_up` and every other Hevy set type
  as `working`; the raw type stays on the stored payload.
- Import upserts the `routine` and `folder` mirrors by Hevy id and never deletes a mirror row
  (amended 2026-10-31). It flips a Routine map row to `missing` when Hevy no longer returns its
  id, and raises a
  drift warning per routine, keyed (routine id, structural or load), when a live routine differs
  from the stored projection of the plan in force. Drift resolves only by a typed override on the
  next WeekPlan or by the next push overwriting it. The engine never adopts an app edit.

## Routines and folders

- Three fixed folders with engine-set titles: Program, Standing, Retired. Created on the first
  `plan apply` that needs one, adopted by exact title when one already exists, refused when two
  share a title. Their ids live on a folder table. Programs never create folders.
- The Routine map is one table: session id, Hevy routine id, folder, status
  `active | retired | missing | unverified`. `plan apply` writes it after a verified write; the one other writer is import flipping a row to `missing`.
- A retired session's routine gets one PUT: title `(unused) <old title>`, folder Retired,
  exercises kept. It becomes a spare. A session needing a routine takes the oldest spare before
  POSTing a new one; a spare mapped to another session is never taken.
- An Exercise without a Hevy template id is created by `plan apply` as a Hevy action in the dry
  run (`create exercise template <title>`), POSTed under the same approval, its id recorded on the
  Exercise row before any routine PUT. Title, exercise type, equipment category and muscle group
  are required Exercise columns for such an exercise, validated at `adopt`.

## Push

- The dry run reads routine `updated_at` from the last import, offline. `plan apply` GETs every
  touched routine live and refuses the whole push before any PUT when one differs, exit 3,
  `error.code = routine_moved`, "run import and re-check". No force flag. The Write plan hash already covers those versions
  (ADR 0006).
- Per routine in map order: PUT, GET back, diff by position on template id, set type, reps or rep
  range, duration, `weight_kg` within 0.001, rest seconds, exercise notes, title and folder. A
  differing read-back stops the run and exits 1, `verify_failed`. The map row is still recorded, status
  `unverified`, so a re-run re-PUTs only unverified routines and those whose stored projection
  differs from live, and sends nothing when all match. A second POST never duplicates a routine.
- Routine body rules and the note format carry from the parity checklist: `weight_kg` is the
  load's Hevy kg only; `Target:`, `Focus:`, `Cues:` per exercise; the week line sits on the first
  exercise because Hevy drops routine-level notes on PUT.

## Write audit

- `hevy/writes.jsonl` in the instance, committed by the next `publish`, never under `.coach/`.
  The client writes it (ADR 0019): the audit is a method of the `HevyClient` protocol, the real
  client appends to the file and `FakeHevy` keeps the same lines in memory, so `services` opens
  no file and there is no fourth seam. Three line kinds (amended 2026-10-31): a **request**
  line before the request is sent (at, method, path, routine id, WeekPlan id, Write plan hash,
  full request body, body digest), a **response** line when the attempt ends after any retries
  (at, method, path, body digest, status or the error, attempts), and a **verify** line after
  each read-back (routine id, verified, diff). A request with no response line is one the
  process died inside. `plan apply` calls `open_audit()` before its first live GET; when the file
  cannot be opened for append the push refuses before any request: exit 3,
  `error.code = audit_unwritable` (`docs/spec/verbs.md`).

## Consequences

- ADR 0010's "deleted on the next push" reads "retired". The glossary gains Spare routine,
  Tombstone, Drift and Write audit.
- The schema (fog) carries: workout versions and tombstones, a folder table, the Routine map with
  four statuses, raw payload columns, the four template columns on Exercise.
- Program authoring (wayfinder #22) validates the template columns at `adopt`. Flag identity
  (wayfinder #23) keys the drift warning. The override catalogue (wayfinder #19) is the only
  route for adopting an app edit. Verb set (wayfinder #16) names the import verb; it pulls Hevy
  alone (the kit is a committed file, ADR 0021).
- Regression tests: a non-allow-listed path raises before any request (run on `hevy/client.py`
  with the recording opener, `tests/hevy/`); a deleted workout leaves a
  tombstone and its sets; an app edit adds a version and the old one stays; a push with a moved
  `updated_at` sends nothing; a failed verify leaves an `unverified` row and the re-run sends only
  that routine; a retire never issues a DELETE.
