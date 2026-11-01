# Schema: tables, keys, views, the export and the migration chain

Spec for wayfinder #29, decided 2026-10-31. The decisions behind it are ADR 0001 (SQLite is the
truth, git sees a sorted export) and ADR 0018 (rows or JSON, ids, refs, no Block table). The
DDL below is hand-written and copied by hand into the engine as `schema.sql`; a contract test
holds that the two match byte for byte. Each migration freezes the DDL it leaves behind
("Schema version and migrations").

The shape in one paragraph: 36 tables. Anything another row refers to by id, or a `query` view
filters on, is a row with a real key; ordered lists and scheme or override params are JSON
text columns. Ids are engine-assigned prefixed strings used unchanged in envelopes, evidence
refs and the export. Nothing derived has a table: Exposure, Match, Miss, e1RM, Week kind,
days off, the anchor, the Block, the cadence signal and a logged set's Exercise are core functions
over these rows. Rows are immutable and a correction is a new row, with three stated kinds of
in-place write ("Updated in place"): the supersede write on four tables, four tables that are a
state rather than a fact about a date, and the two Hevy mirrors that import overwrites.

## Ids

| Prefix | Table | Form |
| --- | --- | --- |
| `pv-` | `program_version` | the sequence: `pv-3` |
| `wp-` | `week_plan` | the Monday: `wp-2026-11-02` |
| `ci-` | `check_in` | the date, a superseding row adds `-2`, `-3`: `ci-2026-11-01-2` |
| `b-` | Block (derived, no table) | its opening date: `b-2026-10-05` |
| `w-` | `workout` (manual only; imports keep the Hevy id) | `w-0001` |
| `d-`, `n-`, `ne-`, `f-`, `fe-`, `o-`, `a-`, `g-`, `m-`, `ph-`, `wi-`, `sn-`, `ac-`, `ss-`, `ir-`, `ak-` | `decision`, `niggle`, `niggle_event`, `follow_up`, `follow_up_event`, `observation`, `annotation`, `goal`, `milestone`, `phase`, `weigh_in`, `sleep_night`, `activity`, `status_span`, `import_run`, `acknowledgement` | max + 1 inside the writing transaction, four digits: `d-0001` |

Session and exercise ids are the authored ids from the program form (`push_a`, `bb_bench_press`).

## Refs

A **ref** is a typed text pointer, `kind:id`, used wherever one column may point at more than
one table: evidence, a note's `about`, an annotation's target, a flag scope, `derived_from`.
Validated by the writing service against the live tables; never a SQL foreign key.

This table is the one ref grammar; every document's examples use these forms. A workout id is
Hevy's (a UUID, `b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13`) or `w-<n>` for a manual one.

| Kind | Form | Example |
| --- | --- | --- |
| `planned_session` | `planned_session:<date>/<session id>`, resolved against the plan in force on that date | `planned_session:2026-11-04/upper-a` |
| `exposure` | `exposure:<workout id>/<exercise id>` | `exposure:b7e2c1a0-5d3f-4e8a-9c21-7f0a4d6b9e13/bb_overhead_press` |
| `workout` | `workout:<workout id>` or `workout:<workout id>/<exercise id>` | `workout:w-0002` |
| `block` | `block:b-<opening date>` (derived, no table) | `block:b-2026-10-05` |
| `check_in` | `check_in:ci-<date>[-n]` | `check_in:ci-2026-10-24` |
| `exercise`, `niggle`, `follow_up`, `decision`, `goal`, `routine`, `milestone`, `phase` | `<kind>:<id>` | `niggle:n-0004`, `routine:3f9d2c7e-1b44-4a0e-8d55-c6a1e2b7f904` |
| `rn` | a research note citation: `rn:<note>.<n>` names a claim of a claims note, `rn:<note> §<n>` a numbered section of a prose note (`research-notes.md`) | `rn:deloads.3` |

A column that only ever points at one table is a plain foreign key (`check_in`, `session_id`,
`exercise_id`, `niggle_id`). A flag key is not a ref: it is `code@<scope kind>:<parts>`,
`validation.md`'s one key grammar. Inside one Draft, `<kind>:@<key>` cites a record the same
file raises under `key = "<key>"`; the writing service rewrites it to the assigned id before the
row is written, so no stored ref carries `@` (`verbs.md`, "A Draft-local key").

## DDL

Conventions: dates are ISO text (`2026-11-02`), instants are ISO text in UTC with seconds,
booleans are `INTEGER CHECK IN (0, 1)`, JSON columns are `TEXT` holding one JSON document, and
every CHECK list over a `kind`, `status`, `because` or `source` column is written by hand here
and in the frozen DDL; the contract test that each list equals the matching code registry
(`validation.md`, `verbs.md`, `overrides.md`, `program.md`) is the guard against the two
drifting. `PRAGMA foreign_keys = ON` is set by the one connection factory (ADR 0001). Every row
a Draft verb writes carries `draft_hash` and `recorded_at`.

The `check_in` column: every table a check-in file may carry rows of has `check_in TEXT
REFERENCES check_in(id)`, NULL when the row came through `record` or `import`: `workout`,
`annotation`, `weigh_in`, `sleep_night`, `activity`, `status_span`, `athlete_note`, `decision`,
`niggle_event`, `follow_up_event`. `observation` has it NOT NULL (check-in file only). No other
table has it; `niggle` and `follow_up` are reached through their first event.

The seven-value reason registry (`pain`, `kit`, `stall`, `fatigue`, `schedule`,
`athlete_request`, `coach_judgement`; ADR 0005) is the `because` CHECK on `override`,
`decision`, `acknowledgement` and `annotation`; a miss tag is the `because` of a `miss_tag`
annotation.

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
  superseded_by   TEXT REFERENCES week_plan(id),  -- the supersede write ("Updated in place")
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
  date        TEXT,                        -- add_session only: the date added; NULL on every other kind
  params      TEXT NOT NULL,               -- JSON, the kind's remaining params
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement')),
  text        TEXT NOT NULL,
  evidence    TEXT,                        -- JSON [ref]
  CHECK ((kind = 'add_session') = (date IS NOT NULL))
);
CREATE UNIQUE INDEX override_one_per_scope   -- one per kind per scope; add_session's scope includes its date
  ON override(plan_id, kind, COALESCE(session_id, ''), COALESCE(exercise_id, ''), COALESCE(date, ''));

CREATE TABLE prescription (                -- frozen at approval, derivation steps included
  plan_id      TEXT NOT NULL REFERENCES week_plan(id),
  session_id   TEXT NOT NULL REFERENCES session(id),
  date         TEXT NOT NULL,
  exercise_id  TEXT NOT NULL REFERENCES exercise(id),
  set_groups   TEXT NOT NULL,              -- JSON [{type, load, load_kg, reps|range|duration_s, rpe}]; load is athlete units for pages, load_kg the Hevy-bound value the Write plan hash covers (ADR 0006)
  derived_from TEXT NOT NULL,              -- 'exposure:<workout>/<exercise>' or 'start_load'
  steps        TEXT NOT NULL,              -- JSON [{step, from, to, cause}]
  flags        TEXT NOT NULL,              -- JSON [Flag]
  change       TEXT NOT NULL,
  PRIMARY KEY (plan_id, session_id, date, exercise_id)
);
```

A planned session has no table. It is `planned_session:<date>/<session>`, derived from the plan
in force on that date; a past plan's sessions are read from its `prescription` rows.

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
  set_type           TEXT NOT NULL CHECK (set_type IN ('warm_up','working','activation','test')),  -- Hevy: warmup -> warm_up, every other Hevy type -> working; the raw type stays in workout.raw
  weight_kg          REAL,
  reps               INTEGER,
  duration_s         INTEGER,
  distance_m         REAL,
  rpe                REAL,
  note               TEXT,
  PRIMARY KEY (workout_id, workout_updated_at, position),
  FOREIGN KEY (workout_id, workout_updated_at) REFERENCES workout(id, updated_at)
);

CREATE TABLE tombstone (                   -- presence events, never withdrawn: 'gone' when Hevy stops returning the id, 'back' when it returns again
  workout_id TEXT NOT NULL,
  noticed_at TEXT NOT NULL,
  kind       TEXT NOT NULL CHECK (kind IN ('gone','back')),
  source     TEXT NOT NULL CHECK (source IN ('event','full')),  -- how import noticed it: the event pull or a full pull
  PRIMARY KEY (workout_id, noticed_at)
);

CREATE TABLE annotation (                  -- applied on read in id order; withdrawn ones skipped
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('discount','repair','load_mode','void','trained_unlogged','cancelled','miss_tag','match')),
  target      TEXT NOT NULL,               -- ref: workout[/exercise] or planned_session
  params      TEXT,                        -- JSON; match names the planned session here
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement')),  -- a miss_tag's because is the miss tag
  text        TEXT,
  withdraws   TEXT REFERENCES annotation(id),
  check_in    TEXT REFERENCES check_in(id),
  draft_hash  TEXT NOT NULL,
  recorded_at TEXT NOT NULL
);

CREATE TABLE weigh_in (                    -- withdrawn by a later row, as annotation; a correction withdraws and re-enters
  id TEXT PRIMARY KEY, date TEXT NOT NULL, kg REAL NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('check_in','hevy','manual')),
  withdraws TEXT REFERENCES weigh_in(id),
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT, recorded_at TEXT NOT NULL
);

CREATE TABLE sleep_night (                 -- as weigh_in; one live row per (night, source) is a record-time check, reading_duplicate
  id TEXT PRIMARY KEY, night TEXT NOT NULL, hours REAL NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('check_in','manual')),
  withdraws TEXT REFERENCES sleep_night(id),
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT, recorded_at TEXT NOT NULL
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
  withdraws TEXT REFERENCES status_span(id),  -- as annotation: a withdrawing row names the one it withdraws
  check_in TEXT REFERENCES check_in(id), draft_hash TEXT NOT NULL, recorded_at TEXT NOT NULL
);
```

### Ledger

```sql
CREATE TABLE check_in (
  id            TEXT PRIMARY KEY,          -- 'ci-<date>[-n]'
  date          TEXT NOT NULL,
  tier          TEXT NOT NULL CHECK (tier IN ('light','deep')),
  window_start  TEXT NOT NULL,             -- derived; the record file may set it on the first row only (week.md)
  window_end    TEXT NOT NULL,
  readiness     TEXT CHECK (readiness IN ('poor','ok','good')),
  read          TEXT NOT NULL,             -- the coach's read, verbatim
  status        TEXT NOT NULL CHECK (status IN ('current','superseded')),
  superseded_by TEXT REFERENCES check_in(id),  -- the supersede write
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
  until         TEXT,                      -- date, inclusive; decline_ceiling's is the Sunday of its week (overrides.md)
  because       TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement')),
  text          TEXT NOT NULL,
  evidence      TEXT,                      -- JSON [ref]
  superseded_by TEXT REFERENCES decision(id),     -- the supersede write
  retired_by    TEXT REFERENCES decision(id),     -- the supersede write, by a 'retire' row
  check_in      TEXT REFERENCES check_in(id),
  draft_hash    TEXT NOT NULL,
  recorded_at   TEXT NOT NULL,
  CHECK (kind NOT IN ('override','leave_warning','decline_ceiling','defer_deep_review') OR until IS NOT NULL)
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

CREATE TABLE niggle_constraint (           -- each event carries the whole set in force from its date;
  id          TEXT PRIMARY KEY,            -- binds under every status but 'resolved' (prescription.md)
  event_id    TEXT NOT NULL REFERENCES niggle_event(id),
  kind        TEXT NOT NULL CHECK (kind IN ('rpe_cap','load_cap','no_added_load','avoid')),
  exercise_id TEXT REFERENCES exercise(id),
  pattern     TEXT,
  value       REAL,                        -- the RPE or the load in athlete units
  CHECK (exercise_id IS NULL OR pattern IS NULL),
  CHECK ((kind IN ('rpe_cap','load_cap')) = (value IS NOT NULL)),
  CHECK (kind <> 'load_cap' OR (exercise_id IS NOT NULL)),
  CHECK (kind <> 'avoid' OR ((exercise_id IS NULL) <> (pattern IS NULL)))
);
-- a 'resolved' niggle_event carries no niggle_constraint rows: checked by `record`, not the DDL

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
  due          TEXT,                       -- kept: the due date set or confirmed; deferred: moved later than the previous due (a record-time check)
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
  superseded_by TEXT REFERENCES goal(id),  -- the supersede write
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
  target      TEXT NOT NULL,               -- JSON: {value} for e1rm and bodyweight_multiple, {load, reps} for load_x_reps (goals.md)
  CHECK ((target_kind = 'load_x_reps') = (json_type(target, '$.load') IS NOT NULL AND json_type(target, '$.reps') IS NOT NULL)),
  CHECK ((target_kind <> 'load_x_reps') = (json_type(target, '$.value') IS NOT NULL))
);

CREATE TABLE phase (                       -- closed in place; one open at a time
  id                   TEXT PRIMARY KEY,
  kind                 TEXT NOT NULL CHECK (kind IN ('deficit','maintenance','surplus')),
  rate_pct_bw_per_week REAL NOT NULL,    -- the kind's registry default when the Draft omits it (goals.md)
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
CREATE UNIQUE INDEX phase_open ON phase((closed IS NULL)) WHERE closed IS NULL;  -- one open Phase of any kind
```

### Hevy

```sql
CREATE TABLE folder (                      -- the mirror: upserted by import and by apply's create, never deleted
  role    TEXT PRIMARY KEY CHECK (role IN ('program','standing','retired')),
  hevy_id TEXT NOT NULL UNIQUE,
  title   TEXT NOT NULL
);

CREATE TABLE routine (                     -- the mirror: upserted by hevy_id by import and by apply's read-back, never deleted
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

Three kinds of in-place write exist and nothing else updates a row; every other correction is a
new row that supersedes or withdraws the old one.

**The supersede write.** When a new row supersedes an old one, the same transaction that
inserts the new row flips the old row's `status` (where the table has one) and sets its forward
pointer. The new row is the audit; the old row stays readable with the pointer to what replaced
it. The partial unique indexes (`week_plan_in_force`, `goal_current`) admit the new row only
because the flip happens in the same transaction.

| Table | Flipped | Pointer set | By |
| --- | --- | --- | --- |
| `week_plan` | `status` to `superseded` | `superseded_by` | `plan apply` of a superseding plan for the same week |
| `check_in` | `status` to `superseded` | `superseded_by` | `checkin record` for the same date with a different hash |
| `goal` | `status` to `superseded` | `superseded_by` | `goal adopt` |
| `decision` | nothing | `superseded_by`, or `retired_by` from a `retire` row | `record` or `checkin record` writing the later Decision |

**State tables.** Four tables are a state rather than a fact about a date:

| Table | Why |
| --- | --- |
| `exercise` | it is the library, not a fact about a date; adopt updates declared fields, the `[[exercise]]` record kind edits the template columns, load mode and equipment kind or declares a new entry (`cutover.md`), `plan apply` sets `hevy_template_id`, `upgrade` inserts new catalogue ids ("The engine catalogue"); the Draft hash on the version or ledger row that caused the write is the audit |
| `observation` | retired is a state of the same noticed pattern; the retiring check-in is the audit |
| `phase` | closed is a state of the same phase; the closing check-in or goal is the audit |
| `routine_map` | it records the live link; status moves with verified writes and imports |

**Hevy mirrors.** `routine` and `folder` are overwritten per Hevy id by `import` and by `plan
apply`'s read-back and create; they mirror the account, so the account is the audit. A mirror
row is never deleted: a routine Hevy no longer returns keeps its row and its `routine_map` row
flips to `missing` (ADR 0011).

## Views

SQLite views take no parameters, so the date-parametrised reads are service functions over a
view. The schema declares these SQL views and nothing else; the maths (e1RM, week kind, Miss,
Match, days off, the anchor, hard sets, the cadence signal) is core functions in Python so each
rule lives in one place.

```sql
CREATE VIEW plan_in_force AS               -- plan_in_force(date): the row whose week covers date
  SELECT id, week, date(week, '+6 days') AS week_end, position, approved_at, write_plan_hash
  FROM week_plan WHERE status = 'approved';

CREATE VIEW workout_current AS             -- latest version of every workout whose latest presence event is not 'gone'
  SELECT w.* FROM workout w
  WHERE w.updated_at = (SELECT max(updated_at) FROM workout WHERE id = w.id)
    AND COALESCE((SELECT kind FROM tombstone t WHERE t.workout_id = w.id
                  ORDER BY noticed_at DESC LIMIT 1), 'back') = 'back';

CREATE VIEW decision_in_force AS           -- the one in-force rule; the service filters by until IS NULL OR until >= date
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

CREATE VIEW weigh_in_current AS            -- the same shape on each withdrawable reading: a withdrawing row is never live
  SELECT r.* FROM weigh_in r
  WHERE r.withdraws IS NULL AND NOT EXISTS (SELECT 1 FROM weigh_in b WHERE b.withdraws = r.id);

CREATE VIEW sleep_night_current AS
  SELECT r.* FROM sleep_night r
  WHERE r.withdraws IS NULL AND NOT EXISTS (SELECT 1 FROM sleep_night b WHERE b.withdraws = r.id);

CREATE VIEW status_span_current AS
  SELECT r.* FROM status_span r
  WHERE r.withdraws IS NULL AND NOT EXISTS (SELECT 1 FROM status_span b WHERE b.withdraws = r.id);
```

A withdrawing row on `weigh_in`, `sleep_night` or `status_span` restates the withdrawn row's
required columns (the record parser copies them) and is itself never read; an annotation's
withdrawing row works the same way. A corrected reading is a withdrawal plus a fresh row in the
same Draft.

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
| `[[follow_up]]` | `follow_up` (first event only), `follow_up_event` |
| `[[decision]]` | `decision`; a `retire` kind also sets `retired_by` on its target |
| `[[annotation]]` | `annotation` |
| `[[note]]` | `athlete_note` |
| `[[workout]]` | `workout` (source `manual`), `logged_set` |
| `[[weigh_in]]`, `[[sleep_night]]`, `[[activity]]` | the table of the same name; a weigh-in or sleep night is withdrawn by a new row whose `withdraws` names it |
| `[[status_span]]` | `status_span`; a withdrawal is a new row whose `withdraws` names the span |
| `[[exercise]]` | `exercise`, in place |
| `[[observation]]` | `observation`, insert or retire in place; check-in file only |

`checkin record` writes `check_in` first and stamps its id on every row the same file carries.
`goal adopt` writes `goal`, `goal_priority_lift`, `milestone` and opens or closes `phase`.
`program adopt` writes `program_version`, `session`, `program_session`, `program_line`,
`acknowledgement` and upserts `exercise`. `plan apply` writes `week_plan`, `override`,
`prescription`, `acknowledgement`, then `routine`, `routine_map`, `folder` and
`exercise.hevy_template_id` as each Hevy write verifies. `import` writes `workout`,
`logged_set`, `tombstone`, `weigh_in` (source `hevy`), `import_run`, upserts
`routine` and `folder`, and flips `routine_map` to `missing`.

## The engine catalogue

The built-in exercise library ships inside the package as `src/coach/store/catalogue.jsonl`:
one JSON object per line in `exercise` column order with `source = 'catalogue'`, the same shape
as `export/exercise.jsonl`, so the export loader reads it. `init` inserts every line into the
new store. `upgrade` merges it: a catalogue id the store lacks is inserted, an id the store has
is left exactly as it stands, whatever the catalogue now says, because the instance's row may
carry an athlete's edit (`[[exercise]]`) or a verified template id. No verb deletes an
`exercise` row. The seed content is `cutover.md`'s (the old library's catalogue pairs).

## Export

`publish` writes `export/`, wholesale, from the store (ADR 0012, 0013):

- `export/manifest.json`: `{"schema_version": <user_version>, "engine_version": "<tag>", "tables": {"<table>": <row count>, ...}}`, keys in that order, tables sorted by name.
- `export/<table>.jsonl`: one file per table, including the Hevy mirror tables and their raw
  payloads; views are never exported. One JSON object per line, keys in column order, `null`
  written as `null`, rows sorted by primary key (multi-column keys compare column by column,
  text by code point, integers numerically).
- No timestamp of the export itself anywhere, so an unchanged store exports byte-identical and
  `publish` on a clean store makes no commit.

**The rebuild.** The export is read in exactly one situation: `.coach/coach.db` is missing and
`export/manifest.json` exists. Any verb that opens the store then rebuilds it first, in the
`store` package, before doing its own work: a fresh database from the DDL of the manifest's
`schema_version` (`schema.sql` or its frozen history, below), every file loaded in foreign-key
order, then the migrations forward. `import` names the rebuild in its result when one happened. With a database
present the export is never read, so no local row can be discarded by a rebuild; to take a newer
export on a second machine the athlete deletes the database file, and `status` says so when the
manifest's row count for any table exceeds the store's (`store_behind_export`, reported by
`status` and a setup-class refusal on every store write until the database is rebuilt or
`publish` has run). Two refusals, setup exit class, never a flag:

- `export_newer_than_engine`: the manifest's `schema_version` is newer than the engine's.
- `store_behind_export`: a table's manifest row count exceeds the store's.

## Schema version and migrations

- `PRAGMA user_version` is the schema version; the envelope's `schema_version` reports it.
- `schema.sql` is the current DDL. A migration that moves from `n` to `n+1` first copies the
  old `schema.sql` to `src/coach/store/schema_history/v<n>.sql`, so the engine carries one
  frozen DDL per past version and the rebuild can build a database at any exported version:
  `schema.sql` when the manifest's version is current, else the history file.
- Migrations are numbered Python functions `m0001` … applied in order inside one transaction;
  a migration that needs a UNIQUE or CHECK change rebuilds the table (ADR 0001).
- `upgrade` is the only verb that moves `user_version` on a live store; the rebuild moves it
  only on the fresh database it is building.
- Before cutover a schema change is "drop the database and re-import" and there are no
  migrations; `schema_history/` is empty and the chain starts at 1 on cutover day.

## Flag codes

One warning joins `validation.md`: `exercise_unmapped` (scope workout; params template id,
title; cleared by an `[[exercise]]` record giving the template id). Import never refuses a
workout for it: the set keeps its raw template id and title and resolves its Exercise on read.
The `exclude` Annotation named in `validation.md` is the `void` kind. `workout_reappeared` is
raised when import appends a `back` tombstone row; the workout's latest version reads again from
that moment, and the warning clears by a `match` or `void` annotation on it. One violation joins
`validation.md`: `reading_duplicate` (scope instance; a second live `weigh_in` for one date and
source, or `sleep_night` for one night and source; cleared by withdrawing one of them).

## Contract tests

- `schema.sql` in the engine is byte-identical to the DDL blocks of this file, in order (the
  one test that reads a spec document, `testing.md`).
- Every CHECK list over a `kind`, `status`, `because` or `source` column equals the matching
  code registry; this is the guard that keeps the hand-written lists honest.
- `PRAGMA foreign_keys` is on from the connection factory (ADR 0001).
- Export of a fixture store, delete the database, rebuild, re-export: byte-identical files.
- The partial unique indexes hold: two approved plans for one week, two current goals, an open
  deficit beside an open surplus, two overrides of one kind on one scope, two `add_session`
  overrides of one session on one date, all refused; two `add_session` overrides of one session
  on two dates are admitted.
- A `back` tombstone row returns the workout's latest version to `workout_current`; a later
  `gone` removes it again.
- No table named `block`, `planned_session`, `exposure`, `match`, `miss`, `e1rm` or
  `progression_state` exists (ADR 0003, 0016, 0018).

## Settles for later tickets

- **Cutover and history import** (settled in `cutover.md`): no old session id becomes a `session`
  row, version 1 is designed fresh; old workouts arrive through `init`'s pull, full
  with `since` NULL and resolve their Exercise on read through `hevy_template_id`.
- **Migration of carried-over state** (settled in `cutover.md`, "The cutover check-in"): one
  hand-written check-in Draft carries the niggles, follow-ups, observations, goal, phase, custom
  template ids and manual workouts through `checkin record`; no converter, no program Draft, no
  `--position`; nothing writes rows directly.
- **Cutover of routines** (settled in `cutover.md`, "The switch"): old routine ids land in
  `routine` through import and none reaches `routine_map`; the first `plan apply` creates fresh
  routines.
- **Fixture instance** (settled in `testing.md`): one small synthetic instance under
  `tests/fixtures/instance/`, its `export/` imported by the same `import`; most tests build rows
  through scenario builders instead.
