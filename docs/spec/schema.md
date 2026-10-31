# Schema: tables, keys, views, the export and the migration chain

Spec for wayfinder #29, decided 2026-10-31. The decisions behind it are ADR 0001 (SQLite is the
truth, git sees a sorted export) and ADR 0018 (rows or JSON, ids, refs, no Block table). The
first build ticket copies the DDL below into the engine as `schema.sql` byte for byte; a
contract test holds that the two match.

The shape in one paragraph: 36 tables. Anything another row refers to by id, or a `query` view
filters on, is a row with a real key; ordered lists and scheme or override params are JSON
text columns. Ids are engine-assigned prefixed strings used unchanged in envelopes, evidence
refs and the export. Nothing derived has a table: Exposure, Match, Miss, e1RM, Week kind,
days off, the anchor, the Block, the cadence signal and a logged set's Exercise are core functions
over these rows. Rows
are immutable; a correction is a new row, and the four exceptions (`exercise`, `observation`,
`phase`, `routine_map`) are named below.

## Ids

| Prefix | Table | Form |
| --- | --- | --- |
| `pv-` | `program_version` | the sequence: `pv-3` |
| `wp-` | `week_plan` | the Monday: `wp-2026-11-02` |
| `ci-` | `check_in` | the date, a superseding row adds `-2`, `-3`: `ci-2026-11-01-2` |
| `b-` | Block (derived, no table) | its opening date: `b-2026-10-05` |
| `w-` | `workout` (manual only; imports keep the Hevy id) | `w-0001` |
| `d-`, `n-`, `ne-`, `f-`, `fe-`, `o-`, `a-`, `g-`, `m-`, `ph-`, `wi-`, `sn-`, `ac-`, `ss-`, `ks-`, `ir-`, `ak-` | `decision`, `niggle`, `niggle_event`, `follow_up`, `follow_up_event`, `observation`, `annotation`, `goal`, `milestone`, `phase`, `weigh_in`, `sleep_night`, `activity`, `status_span`, `kit_snapshot`, `import_run`, `acknowledgement` | max + 1 inside the writing transaction, four digits: `d-0001` |

Session and exercise ids are the authored ids from the program form (`push_a`, `bb_bench_press`).

## Refs

A **ref** is a typed text pointer, `kind:id`, used wherever one column may point at more than
one table: evidence, a note's `about`, an annotation's target, a flag scope, `derived_from`.
Validated by the writing service against the live tables; never a SQL foreign key.

| Kind | Form |
| --- | --- |
| `planned_session` | `planned_session:<plan id>/<session id>/<date>` |
| `exposure` | `exposure:<workout id>/<exercise id>` |
| `workout` | `workout:<workout id>` or `workout:<workout id>/<exercise id>` |
| `exercise`, `niggle`, `follow_up`, `decision`, `check_in`, `goal`, `routine`, `milestone`, `phase` | `<kind>:<id>` |
| `rn` | a research note citation, `rn:<note> §<n>` |

A column that only ever points at one table is a plain foreign key (`check_in`, `session_id`,
`exercise_id`, `niggle_id`).

## DDL

Conventions: dates are ISO text (`2026-11-02`), instants are ISO text in UTC with seconds,
booleans are `INTEGER CHECK IN (0, 1)`, JSON columns are `TEXT` holding one JSON document, and
every CHECK over a `kind` column is generated at build time from the matching code registry
(`validation.md`, `verbs.md`, `overrides.md`, `program.md`). `PRAGMA foreign_keys = ON` is set
by the one connection factory (ADR 0001). Every row a Draft verb writes carries `draft_hash` and
`recorded_at`; every ledger row carries a nullable `check_in`.

### Program

```sql
CREATE TABLE session (
  id            TEXT PRIMARY KEY,
  introduced_in TEXT NOT NULL              -- 'pv-<n>' or 'n-<n>': the version or niggle that first named it
);

CREATE TABLE exercise (                    -- updated in place; the one library
  id                 TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  load_mode          TEXT NOT NULL CHECK (load_mode IN ('total','per_hand_x2','single_implement','bodyweight','assisted','band','duration','distance')),
  equipment_kind     TEXT NOT NULL CHECK (equipment_kind IN ('barbell','dumbbell','kettlebell','leg_attachment','vest','machine','cable','band','bodyweight')),
  pattern            TEXT NOT NULL,
  muscles            TEXT NOT NULL,        -- JSON {primary:[], secondary:[]}
  increment          REAL,                 -- athlete units; NULL means the location's
  hevy_title         TEXT,
  hevy_exercise_type TEXT,
  hevy_equipment     TEXT,
  hevy_muscle_group  TEXT,
  hevy_template_id   TEXT UNIQUE,          -- catalogue seed for built-ins, an [[exercise]] record, or plan apply after a verified create
  source             TEXT NOT NULL CHECK (source IN ('catalogue','draft','record'))
);

CREATE TABLE program_version (
  id          TEXT PRIMARY KEY,            -- 'pv-<sequence>'
  sequence    INTEGER NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('amend','redesign')),
  because     TEXT NOT NULL,
  emphasis    TEXT NOT NULL CHECK (emphasis IN ('hypertrophy','strength','maintenance')),
  location    TEXT NOT NULL,               -- a [location.<name>] in coach.toml
  position    TEXT NOT NULL,               -- the rotation week adopt starts at
  adopted     TEXT NOT NULL,               -- date
  form        TEXT NOT NULL,               -- JSON: the whole filled form, the audit copy
  schedule    TEXT NOT NULL,               -- JSON: rotation list and week tables
  dose        TEXT NOT NULL,               -- JSON: filled [dose]
  deload      TEXT NOT NULL,               -- JSON: filled [deload]
  draft_hash  TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE program_session (
  version_id     TEXT NOT NULL REFERENCES program_version(id),
  session_id     TEXT NOT NULL REFERENCES session(id),
  title          TEXT NOT NULL,
  kind           TEXT NOT NULL CHECK (kind IN ('lifting','conditioning','practice','coach_led')),
  tier           TEXT NOT NULL CHECK (tier IN ('core','optional')),
  cadence        TEXT NOT NULL CHECK (cadence IN ('weekly','standing','daily')),
  location       TEXT,                     -- NULL means the version's
  minutes        INTEGER,
  scheme         TEXT,                     -- JSON, conditioning only
  estimated_sets TEXT,                     -- JSON {muscle: n}, coach-led only
  PRIMARY KEY (version_id, session_id)
);

CREATE TABLE program_line (
  version_id  TEXT NOT NULL,
  session_id  TEXT NOT NULL,
  exercise_id TEXT NOT NULL REFERENCES exercise(id),
  position    INTEGER NOT NULL,            -- order within the session
  load_mode   TEXT,                        -- NULL means the exercise's
  set_groups  TEXT NOT NULL,               -- JSON [{count, type, reps|duration_s, rpe}]
  rest_s      INTEGER,
  cues        TEXT,
  scheme      TEXT NOT NULL,               -- JSON {name, ...params}, filled
  start_load  REAL,                        -- athlete units, per hand where per hand
  superset    TEXT,
  PRIMARY KEY (version_id, session_id, exercise_id),
  FOREIGN KEY (version_id, session_id) REFERENCES program_session(version_id, session_id),
  UNIQUE (version_id, session_id, position)
);

CREATE TABLE rehab_session (               -- a session a niggle carries, never in a version
  session_id  TEXT PRIMARY KEY REFERENCES session(id),
  niggle_id   TEXT NOT NULL REFERENCES niggle(id),
  title       TEXT NOT NULL,
  tier        TEXT NOT NULL DEFAULT 'optional' CHECK (tier IN ('core','optional')),
  cadence     TEXT NOT NULL CHECK (cadence IN ('standing','daily')),
  location    TEXT,
  lines       TEXT NOT NULL,               -- JSON: program_line rows minus the keys, scheme hold
  draft_hash  TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE acknowledgement (             -- frozen on a plan or a version, never deleted
  id          TEXT PRIMARY KEY,
  plan_id     TEXT REFERENCES week_plan(id),
  version_id  TEXT REFERENCES program_version(id),
  key         TEXT NOT NULL,               -- 'code@scope-ref'
  params_hash TEXT NOT NULL,
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement')),
  text        TEXT NOT NULL,
  evidence    TEXT,                        -- JSON [ref]
  CHECK ((plan_id IS NULL) <> (version_id IS NULL)),
  UNIQUE (plan_id, key),
  UNIQUE (version_id, key)
);
```

### Week

```sql
CREATE TABLE week_plan (
  id              TEXT PRIMARY KEY,        -- 'wp-<monday>'
  week            TEXT NOT NULL,           -- the Monday
  position        TEXT NOT NULL,           -- the confirmed rotation week
  status          TEXT NOT NULL CHECK (status IN ('approved','superseded')),
  approved_at     TEXT NOT NULL,
  write_plan_hash TEXT NOT NULL,
  location        TEXT,                    -- a one_off_week location, else NULL
  superseded_by   TEXT REFERENCES week_plan(id),
  draft_hash      TEXT NOT NULL,
  recorded_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX week_plan_in_force ON week_plan(week) WHERE status = 'approved';

CREATE TABLE override (
  id          TEXT PRIMARY KEY,
  plan_id     TEXT NOT NULL REFERENCES week_plan(id),
  kind        TEXT NOT NULL CHECK (kind IN ('light_week','minimum_week','one_off_week','move_session','drop_session','add_session','relocate_session','swap_exercise','pin_load','hold','restate_sets','drop_line')),
  session_id  TEXT REFERENCES session(id),
  exercise_id TEXT REFERENCES exercise(id),
  params      TEXT NOT NULL,               -- JSON, the kind's params
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement')),
  text        TEXT NOT NULL,
  evidence    TEXT                         -- JSON [ref]
);
CREATE UNIQUE INDEX override_one_per_scope
  ON override(plan_id, kind, COALESCE(session_id, ''), COALESCE(exercise_id, ''));

CREATE TABLE prescription (                -- frozen at approval, derivation steps included
  plan_id      TEXT NOT NULL REFERENCES week_plan(id),
  session_id   TEXT NOT NULL REFERENCES session(id),
  date         TEXT NOT NULL,
  exercise_id  TEXT NOT NULL REFERENCES exercise(id),
  set_groups   TEXT NOT NULL,              -- JSON [{type, load, load_kg, reps|range|duration_s, rpe}]
  derived_from TEXT NOT NULL,              -- 'exposure:<workout>/<exercise>' or 'start_load'
  steps        TEXT NOT NULL,              -- JSON [{step, from, to, cause}]
  flags        TEXT NOT NULL,              -- JSON [Flag]
  change       TEXT NOT NULL,
  PRIMARY KEY (plan_id, session_id, date, exercise_id)
);
```

A planned session has no table. It is `planned_session:<plan>/<session>/<date>`, derived from
the plan in force; a past plan's sessions are read from its `prescription` rows.

### Log

```sql
CREATE TABLE workout (                     -- append-only, versioned by (id, updated_at)
  id          TEXT NOT NULL,               -- the Hevy id, or 'w-<n>' when manual
  updated_at  TEXT NOT NULL,               -- Hevy's, or recorded_at when manual
  source      TEXT NOT NULL CHECK (source IN ('hevy','manual')),
  date        TEXT NOT NULL,
  title       TEXT,
  routine_id  TEXT,                        -- Hevy routine id when Hevy reports one
  session_id  TEXT REFERENCES session(id), -- manual coach-led only; Match is derived otherwise
  minutes     INTEGER,
  session_rpe REAL,
  notes       TEXT,
  raw         TEXT,                        -- JSON, the Hevy payload
  check_in    TEXT REFERENCES check_in(id),
  draft_hash  TEXT,
  recorded_at TEXT NOT NULL,
  PRIMARY KEY (id, updated_at)
);

CREATE TABLE logged_set (
  workout_id         TEXT NOT NULL,
  workout_updated_at TEXT NOT NULL,
  position           INTEGER NOT NULL,
  hevy_template_id   TEXT,                 -- the Exercise is resolved on read through exercise.hevy_template_id
  hevy_title         TEXT,
  set_type           TEXT NOT NULL CHECK (set_type IN ('warm_up','working','activation','test')),
  weight_kg          REAL,
  reps               INTEGER,
  duration_s         INTEGER,
  distance_m         REAL,
  rpe                REAL,
  note               TEXT,
  PRIMARY KEY (workout_id, workout_updated_at, position),
  FOREIGN KEY (workout_id, workout_updated_at) REFERENCES workout(id, updated_at)
);

CREATE TABLE tombstone (                   -- never withdrawn
  workout_id TEXT NOT NULL,
  noticed_at TEXT NOT NULL,
  source     TEXT NOT NULL CHECK (source IN ('event','full_pull')),
  PRIMARY KEY (workout_id, noticed_at)
);

CREATE TABLE annotation (                  -- applied on read in id order; withdrawn ones skipped
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('discount','repair','load_mode','void','trained_unlogged','cancelled','miss_tag','match')),
  target      TEXT NOT NULL,               -- ref: workout[/exercise] or planned_session
  params      TEXT,                        -- JSON; match names the planned session here
  because     TEXT NOT NULL,
  text        TEXT,
  withdraws   TEXT REFERENCES annotation(id),
  check_in    TEXT REFERENCES check_in(id),
  draft_hash  TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE weigh_in (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, kg REAL NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('check_in','hevy','manual')),
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT, recorded_at TEXT NOT NULL
);

CREATE TABLE sleep_night (
  id TEXT PRIMARY KEY, night TEXT NOT NULL, hours REAL NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('check_in','hevy','manual')),
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT, recorded_at TEXT NOT NULL,
  UNIQUE (night, source)
);

CREATE TABLE activity (                    -- hand-entered bouts; conditioning workouts stay a view
  id TEXT PRIMARY KEY, date TEXT NOT NULL, kind TEXT NOT NULL,
  minutes INTEGER NOT NULL, distance_km REAL, rpe REAL NOT NULL,
  quality INTEGER NOT NULL CHECK (quality IN (0, 1)), text TEXT,
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);

CREATE TABLE status_span (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('ill','injured','travel','no_training')),
  from_date TEXT NOT NULL, to_date TEXT,   -- NULL is open-ended
  text TEXT,
  withdrawn_by TEXT REFERENCES status_span(id),
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);
```

### Ledger

```sql
CREATE TABLE check_in (
  id            TEXT PRIMARY KEY,          -- 'ci-<date>[-n]'
  date          TEXT NOT NULL,
  tier          TEXT NOT NULL CHECK (tier IN ('light','deep')),
  window_start  TEXT NOT NULL,
  window_end    TEXT NOT NULL,
  read          TEXT NOT NULL,             -- the coach's read, verbatim
  status        TEXT NOT NULL CHECK (status IN ('current','superseded')),
  superseded_by TEXT REFERENCES check_in(id),
  draft_hash    TEXT NOT NULL,
  recorded_at   TEXT NOT NULL
);

CREATE TABLE observation (                 -- retired in place: the retiring check-in is the audit
  id               TEXT PRIMARY KEY,
  raised           TEXT NOT NULL,          -- date
  text             TEXT NOT NULL,
  evidence         TEXT,                   -- JSON [ref]
  check_in         TEXT NOT NULL REFERENCES check_in(id),
  retired_at       TEXT,
  retired_because  TEXT,
  retired_check_in TEXT REFERENCES check_in(id),
  draft_hash       TEXT NOT NULL,
  recorded_at      TEXT NOT NULL,
  CHECK ((retired_at IS NULL) = (retired_check_in IS NULL))
);

CREATE TABLE athlete_note (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, text TEXT NOT NULL,
  about TEXT,                              -- ref: planned_session, exercise, niggle or follow_up only
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);

CREATE TABLE decision (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('override','park_session','resume_session','leave_warning','training_max','safety_ceiling','activity_cap','decline_ceiling','defer_deep_review','against_research','retire')),
  session_id    TEXT REFERENCES session(id),      -- pulled out of params: the supersede rule keys on it
  exercise_id   TEXT REFERENCES exercise(id),     -- likewise
  params        TEXT NOT NULL,             -- JSON, the kind's remaining params
  until         TEXT,                      -- date
  because       TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement')),
  text          TEXT NOT NULL,
  evidence      TEXT,                      -- JSON [ref]
  superseded_by TEXT REFERENCES decision(id),
  retired_by    TEXT REFERENCES decision(id),     -- set by a 'retire' row in the same transaction
  check_in      TEXT REFERENCES check_in(id),
  draft_hash    TEXT NOT NULL,
  recorded_at   TEXT NOT NULL
);

CREATE TABLE niggle (
  id               TEXT PRIMARY KEY,
  opened           TEXT NOT NULL,          -- date
  site             TEXT NOT NULL,
  rehab_session_id TEXT REFERENCES session(id),
  draft_hash       TEXT NOT NULL,
  recorded_at      TEXT NOT NULL
);

CREATE TABLE niggle_event (                -- status in force is the latest event's
  id          TEXT PRIMARY KEY,
  niggle_id   TEXT NOT NULL REFERENCES niggle(id),
  date        TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('reported','aggravated','easing','chronic','resolved')),
  text        TEXT,
  check_in    TEXT REFERENCES check_in(id),
  draft_hash  TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE niggle_constraint (           -- each event carries the whole set in force from its date
  id          TEXT PRIMARY KEY,
  event_id    TEXT NOT NULL REFERENCES niggle_event(id),
  kind        TEXT NOT NULL CHECK (kind IN ('rpe_cap','load_cap','no_added_load','avoid')),
  exercise_id TEXT REFERENCES exercise(id),
  pattern     TEXT,
  value       REAL,                        -- the RPE or the load in athlete units
  CHECK (kind <> 'rpe_cap' OR value IS NOT NULL),
  CHECK (kind <> 'load_cap' OR (value IS NOT NULL AND exercise_id IS NOT NULL)),
  CHECK (kind <> 'avoid' OR ((exercise_id IS NULL) <> (pattern IS NULL)))
);

CREATE TABLE follow_up (
  id TEXT PRIMARY KEY, raised TEXT NOT NULL, text TEXT NOT NULL,
  about TEXT,                              -- ref; 'exercise:<id>' for a dated milestone
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);

CREATE TABLE follow_up_event (             -- the raising event is 'kept' with the first due date
  id           TEXT PRIMARY KEY,
  follow_up_id TEXT NOT NULL REFERENCES follow_up(id),
  date         TEXT NOT NULL,
  kind         TEXT NOT NULL CHECK (kind IN ('deferred','kept','resolved','dropped')),
  due          TEXT,                       -- required for deferred and kept
  text         TEXT,
  check_in     TEXT REFERENCES check_in(id),
  draft_hash   TEXT NOT NULL,
  recorded_at  TEXT NOT NULL,
  CHECK (kind NOT IN ('deferred','kept') OR due IS NOT NULL)
);

CREATE TABLE goal (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL CHECK (kind IN ('hypertrophy','strength')),
  why           TEXT NOT NULL,
  because       TEXT NOT NULL,
  adopted       TEXT NOT NULL,             -- date
  status        TEXT NOT NULL CHECK (status IN ('current','superseded')),
  superseded_by TEXT REFERENCES goal(id),
  draft_hash    TEXT NOT NULL,
  recorded_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX goal_current ON goal(status) WHERE status = 'current';

CREATE TABLE goal_priority_lift (
  goal_id     TEXT NOT NULL REFERENCES goal(id),
  rank        INTEGER NOT NULL,
  exercise_id TEXT NOT NULL REFERENCES exercise(id),
  PRIMARY KEY (goal_id, rank),
  UNIQUE (goal_id, exercise_id)
);

CREATE TABLE milestone (                   -- a restated milestone on a new Goal gets a new id
  id          TEXT PRIMARY KEY,
  goal_id     TEXT NOT NULL REFERENCES goal(id),
  exercise_id TEXT NOT NULL REFERENCES exercise(id),
  target_kind TEXT NOT NULL CHECK (target_kind IN ('e1rm','load_x_reps','bodyweight_multiple')),
  target      TEXT NOT NULL                -- JSON: {value} or {load, reps}
);

CREATE TABLE phase (                       -- closed in place; one open at a time
  id                   TEXT PRIMARY KEY,
  kind                 TEXT NOT NULL CHECK (kind IN ('deficit','maintenance','surplus')),
  rate_pct_bw_per_week REAL NOT NULL,
  until_kind           TEXT NOT NULL CHECK (until_kind IN ('date','bodyweight_at_or_below','bodyweight_at_or_above','coachs_call')),
  until_value          TEXT,
  opened               TEXT NOT NULL,      -- date
  opened_by            TEXT NOT NULL,      -- ref: check_in or goal
  opened_because       TEXT NOT NULL,
  closed               TEXT,
  closed_by            TEXT,               -- ref: check_in or goal
  closed_because       TEXT,
  draft_hash           TEXT NOT NULL,
  recorded_at          TEXT NOT NULL,
  CHECK ((closed IS NULL) = (closed_by IS NULL) AND (closed IS NULL) = (closed_because IS NULL))
);
CREATE UNIQUE INDEX phase_open ON phase(kind) WHERE closed IS NULL;
```

### Hevy

```sql
CREATE TABLE folder (
  role    TEXT PRIMARY KEY CHECK (role IN ('program','standing','retired')),
  hevy_id TEXT NOT NULL UNIQUE,
  title   TEXT NOT NULL
);

CREATE TABLE routine (                     -- the mirror, rewritten by import and by apply's read-back
  hevy_id     TEXT PRIMARY KEY,
  updated_at  TEXT NOT NULL,
  title       TEXT NOT NULL,
  folder_id   TEXT,                        -- Hevy folder id, any folder
  raw         TEXT NOT NULL,               -- JSON
  imported_at TEXT NOT NULL
);

CREATE TABLE routine_map (                 -- written by plan apply after a verified write; import may flip to missing
  session_id    TEXT PRIMARY KEY REFERENCES session(id),
  routine_id    TEXT NOT NULL REFERENCES routine(hevy_id),
  status        TEXT NOT NULL CHECK (status IN ('active','retired','missing','unverified')),
  last_verified TEXT,
  plan_id       TEXT REFERENCES week_plan(id),
  written_at    TEXT NOT NULL
);

CREATE TABLE kit_snapshot (                -- a plate-pool achievable.json as fetched
  id           TEXT PRIMARY KEY,
  location     TEXT NOT NULL,
  url          TEXT NOT NULL,
  fetched_at   TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  payload      TEXT NOT NULL,              -- JSON
  UNIQUE (location, content_hash)
);

CREATE TABLE import_run (
  id          TEXT PRIMARY KEY,
  at          TEXT NOT NULL,
  since       TEXT,                        -- NULL on a full pull
  kind        TEXT NOT NULL CHECK (kind IN ('event','full')),
  only        TEXT,                        -- '--only' argument, NULL for everything
  summary     TEXT NOT NULL                -- JSON: counts per table
);
```

The Hevy write audit is a file, `hevy/writes.jsonl`, not a table (ADR 0001, 0011).

### Updated in place

Four tables break append-only, each for a stated reason; everything else is insert-only and a
correction is a new row that supersedes or withdraws the old one.

| Table | Why |
| --- | --- |
| `exercise` | it is the library, not a fact about a date; adopt updates declared fields, the `[[exercise]]` record kind edits the template columns, load mode and equipment kind or declares a new entry (`cutover.md`), `plan apply` sets `hevy_template_id`; the Draft hash on the version or ledger row that caused the write is the audit |
| `observation` | retired is a state of the same noticed pattern; the retiring check-in is the audit |
| `phase` | closed is a state of the same phase; the closing check-in or goal is the audit |
| `routine_map` | it records the live link; status moves with verified writes and imports |

## Views

SQLite views take no parameters, so the date-parametrised reads are service functions over a
view. The schema declares these SQL views and nothing else; the maths (e1RM, week kind, Miss,
Match, days off, the anchor, hard sets, the cadence signal) is core functions in Python so each
rule lives in one place.

```sql
CREATE VIEW plan_in_force AS               -- plan_in_force(date): the row whose week covers date
  SELECT id, week, date(week, '+6 days') AS week_end, position, approved_at, write_plan_hash, location
  FROM week_plan WHERE status = 'approved';

CREATE VIEW workout_current AS             -- latest version of every workout Hevy still has
  SELECT w.* FROM workout w
  WHERE w.updated_at = (SELECT max(updated_at) FROM workout WHERE id = w.id)
    AND NOT EXISTS (SELECT 1 FROM tombstone t WHERE t.workout_id = w.id);

CREATE VIEW decision_in_force AS           -- filter by until >= date in the service
  SELECT * FROM decision WHERE superseded_by IS NULL AND retired_by IS NULL AND kind <> 'retire';

CREATE VIEW niggle_current AS              -- latest event per niggle
  SELECT n.id AS niggle_id, n.site, n.rehab_session_id, e.id AS event_id, e.date, e.status
  FROM niggle n JOIN niggle_event e ON e.niggle_id = n.id
  WHERE e.id = (SELECT id FROM niggle_event WHERE niggle_id = n.id ORDER BY date DESC, id DESC LIMIT 1);

CREATE VIEW follow_up_current AS           -- latest event per follow-up
  SELECT f.id AS follow_up_id, f.text, f.about, e.kind, e.due
  FROM follow_up f JOIN follow_up_event e ON e.follow_up_id = f.id
  WHERE e.id = (SELECT id FROM follow_up_event WHERE follow_up_id = f.id ORDER BY date DESC, id DESC LIMIT 1);

CREATE VIEW annotation_current AS          -- withdrawn ones removed
  SELECT a.* FROM annotation a
  WHERE NOT EXISTS (SELECT 1 FROM annotation b WHERE b.withdraws = a.id);
```

The six `query` views of `verbs.md` (`exposures`, `readings`, `flags`, `lines`, `routines`,
`ledger`) are service reads composed from these views and the core functions; `readings` is
the union of `weigh_in`, `sleep_night`, `activity` and the Activity derived from each
conditioning workout. The `lines` view unions `program_line` of the version in force with
`rehab_session.lines` of open niggles.

## Record kinds to tables

The twelve ledger record kinds (`verbs.md`) and what each writes:

| Kind | Writes |
| --- | --- |
| `[[niggle]]` | `niggle` (first event only), `niggle_event`, its `niggle_constraint` rows, `session` + `rehab_session` when it carries one |
| `[[followup]]` | `follow_up` (first event only), `follow_up_event` |
| `[[decision]]` | `decision`; a `retire` kind also sets `retired_by` on its target |
| `[[annotation]]` | `annotation` |
| `[[note]]` | `athlete_note` |
| `[[workout]]` | `workout` (source `manual`), `logged_set` |
| `[[weigh_in]]`, `[[sleep_night]]`, `[[activity]]` | the table of the same name |
| `[[status_span]]` | `status_span`; a withdrawal is a new row with nothing but `withdrawn_by` pointing back |
| `[[exercise]]` | `exercise`, in place |
| `[[observation]]` | `observation`, insert or retire in place; check-in file only |

`checkin record` writes `check_in` first and stamps its id on every row the same file carries.
`goal adopt` writes `goal`, `goal_priority_lift`, `milestone` and opens or closes `phase`.
`program adopt` writes `program_version`, `session`, `program_session`, `program_line`,
`acknowledgement` and upserts `exercise`. `plan apply` writes `week_plan`, `override`,
`prescription`, `acknowledgement`, then `routine`, `routine_map`, `folder` and
`exercise.hevy_template_id` as each Hevy write verifies. `import` writes `workout`,
`logged_set`, `tombstone`, `routine`, `weigh_in` (source `hevy`), `kit_snapshot`,
`import_run`, and flips `routine_map` to `missing`.

## Export

`publish` writes `export/`, wholesale, from the store (ADR 0012, 0013):

- `export/manifest.json`: `{"schema_version": <user_version>, "engine_version": "<tag>", "tables": {"<table>": <row count>, ...}}`, keys in that order, tables sorted by name.
- `export/<table>.jsonl`: one file per table, including the Hevy mirror tables and their raw
  payloads; views are never exported. One JSON object per line, keys in column order, `null`
  written as `null`, rows sorted by primary key (multi-column keys compare column by column,
  text by code point, integers numerically).
- No timestamp of the export itself anywhere, so an unchanged store exports byte-identical and
  `publish` on a clean store makes no commit.

`import` creates a fresh database at the manifest's `schema_version`, loads every file in
foreign-key order, then migrates forward (below). A manifest whose `schema_version` is newer
than the engine's stops the verb with the setup exit class and the reason
`export_newer_than_engine`; it is never a flag.

## Schema version and migrations

- `PRAGMA user_version` is the schema version; the envelope's `schema_version` reports it.
- Migrations are numbered Python functions `m0001` … applied in order inside one transaction;
  a migration that needs a UNIQUE or CHECK change rebuilds the table (ADR 0001).
- `upgrade` is the only verb that moves `user_version` on a live store; `import` moves it only
  on the fresh database it is building.
- Before cutover a schema change is "drop the database and re-import" and there are no
  migrations; the chain starts at 1 on cutover day.

## Flag codes

One warning joins `validation.md`: `exercise_unmapped` (scope workout; params template id,
title; cleared by an `[[exercise]]` record giving the template id). Import never refuses a
workout for it: the set keeps a NULL `exercise_id` and its raw title. The `exclude` Annotation
named in `validation.md` is the `void` kind; `workout_reappeared` clears by `match` or `void`.

## Contract tests

- `schema.sql` in the engine is byte-identical to the DDL blocks of this file, in order.
- Every CHECK list over a `kind`, `status`, `because` or `source` column equals the matching
  code registry.
- `PRAGMA foreign_keys` is on from the connection factory (ADR 0001).
- Export of a fixture store, re-import, re-export: byte-identical files.
- The partial unique indexes hold: two approved plans for one week, two current goals, two open
  phases, two overrides of one kind on one scope, all refused.
- No table named `block`, `planned_session`, `exposure`, `match`, `miss`, `e1rm` or
  `progression_state` exists (ADR 0003, 0016, 0018).

## Settles for later tickets

- **Cutover and history import** (settled in `cutover.md`): no old session id becomes a `session`
  row, version 1 is designed fresh; old workouts arrive through the ordinary `import --full`
  with `since` NULL and resolve their Exercise on read through `hevy_template_id`.
- **Migration of carried-over state** (fog): the converter writes one ledger Draft (niggles,
  follow-ups, observations, goal, phase, custom template ids, three manual workouts); there is
  no program Draft to convert and no `--position`; nothing writes rows directly.
- **Cutover of routines** (fog): old routine ids land in `routine` through import; whether any
  reach `routine_map` is that ticket's call.
- **Fixture instance** (settled in `testing.md`): one small synthetic instance under
  `tests/fixtures/instance/`, its `export/` imported by the same `import`; most tests build rows
  through scenario builders instead.
