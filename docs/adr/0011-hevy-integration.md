---
status: accepted
date: 2026-10-27
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
  audit lines. 429: sleep 30 s, three tries; a token bucket on writes; reads never throttled. A
  fixture transport that refuses writes and a fake Hevy that bumps `updated_at`, drops routine
  notes on PUT and can corrupt a read-back carry over for tests.

## Import

- One verb pulls workouts (events since the last import minus a 10-minute overlap; `--full`
  re-lists everything), routines, folders, exercise templates and body measurements, and stores
  normalised rows with the raw payload kept on the row. No cache directory. Exposure, Match, e1RM
  and the Activity of a conditioning workout stay views; the `activity` table holds hand-entered bouts only (ADR 0018).
- A Workout is versioned by (Hevy id, `updated_at`). An app edit appends a version; reads take the
  latest. A delete event, or an id missing from a full pull, appends a tombstone (id, noticed at,
  source `event` or `full pull`). Reads skip tombstoned workouts; the rows stay; a tombstone is
  never withdrawn. An id that reappears gets a new version and a warning, not an undo.
- Import flips a Routine map row to `missing` when Hevy no longer returns its id, and raises a
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
  touched routine live and refuses the whole push before any PUT when one differs, exit 3, "run
  import and re-check". No force flag. The Write plan hash already covers those versions
  (ADR 0006).
- Per routine in map order: PUT, GET back, diff by position on template id, set type, reps or rep
  range, duration, `weight_kg` within 0.001, rest seconds, exercise notes, title and folder. A
  differing read-back stops the run and exits 1. The map row is still recorded, status
  `unverified`, so a re-run re-PUTs only unverified routines and those whose stored projection
  differs from live, and sends nothing when all match. A second POST never duplicates a routine.
- Routine body rules and the note format carry from the parity checklist: `weight_kg` is the
  load's Hevy kg only; `Target:`, `Focus:`, `Cues:` per exercise; the week line sits on the first
  exercise because Hevy drops routine-level notes on PUT.

## Write audit

- `hevy/writes.jsonl` in the instance, committed by the next `publish`, never under `.coach/`.
  One line per request after retries (at, method, path, status, routine id, WeekPlan id, Write
  plan hash, full request body, body digest) and one per verify (routine id, verified, diff).
  Appended at request time; a write refuses to run when the file cannot be opened for append.

## Consequences

- ADR 0010's "deleted on the next push" reads "retired". The glossary gains Spare routine,
  Tombstone, Drift and Write audit.
- The schema (fog) carries: workout versions and tombstones, a folder table, the Routine map with
  four statuses, raw payload columns, the four template columns on Exercise.
- Program authoring (wayfinder #22) validates the template columns at `adopt`. Flag identity
  (wayfinder #23) keys the drift warning. The override catalogue (wayfinder #19) is the only
  route for adopting an app edit. Verb set (wayfinder #16) names the import verb, which also
  fetches the plate-pool snapshot (ADR 0008).
- Regression tests: a non-allow-listed path raises before any request; a deleted workout leaves a
  tombstone and its sets; an app edit adds a version and the old one stays; a push with a moved
  `updated_at` sends nothing; a failed verify leaves an `unverified` row and the re-run sends only
  that routine; a retire never issues a DELETE.
