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
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement','progress')),
  text        TEXT NOT NULL,
  evidence    TEXT,                        -- JSON [ref]
  CHECK ((plan_id IS NULL) <> (version_id IS NULL)),
  UNIQUE (plan_id, key),
  UNIQUE (version_id, key)
);

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
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement','progress')),
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
  position     INTEGER NOT NULL,           -- order within the plan
  set_groups   TEXT NOT NULL,              -- JSON [{type, load, load_kg, reps|range|duration_s, rpe}]; load is athlete units for pages, load_kg the Hevy-bound value the Write plan hash covers (ADR 0006)
  derived_from TEXT NOT NULL,              -- 'exposure:<workout>/<exercise>' or 'start_load'
  steps        TEXT NOT NULL,              -- JSON [{step, from, to, cause}]
  flags        TEXT NOT NULL,              -- JSON [Flag]
  change       TEXT NOT NULL,
  PRIMARY KEY (plan_id, session_id, date, exercise_id)
);

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
  because     TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement','progress')),  -- a miss_tag's because is the miss tag
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
  kind          TEXT NOT NULL CHECK (kind IN ('override','park_session','resume_session','leave_warning','training_max','safety_ceiling','activity_cap','decline_ceiling','defer_deep_review','against_research','ladder_rung','retire')),
  session_id    TEXT REFERENCES session(id),      -- pulled out of params: the supersede rule keys on it
  exercise_id   TEXT REFERENCES exercise(id),     -- likewise
  params        TEXT NOT NULL,             -- JSON, the kind's remaining params
  until         TEXT,                      -- date, inclusive; decline_ceiling's is the Sunday of its week (overrides.md)
  because       TEXT NOT NULL CHECK (because IN ('pain','kit','stall','fatigue','schedule','athlete_request','coach_judgement','progress')),
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
