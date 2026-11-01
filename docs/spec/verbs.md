# Verb set and output budgets

The sixteen verbs the agent, the hooks and a human terminal can run, what each returns by
default, what a second identical call does, and the rule for adding one. Decided 2026-10-31
(wayfinder #16). The architecture they sit on is ADR 0002: a CLI over plain service functions,
one JSON envelope per call, one declaration per verb generating `--help`, `schema` and the
contract tests. Amended 2026-10-31 by [Verb, hook and validation amendments](https://github.com/joeuk89/strength-coach/issues/43):
the `writes` declaration field, `--dry-run` on every asked verb, the exit-class codes, the
Draft-local key, `notes` in the plan Draft, and what `status` and `query` return.

## Budget and admission

A **verb** is one leaf the agent can run: `coach status` is one, `coach checkin open` and
`coach checkin record` are two. A noun groups leaves only where two or more actions share it.

The v1 set is sixteen leaves and that is the cap. A leaf is added later for exactly two reasons:

1. A record the agent must change that no existing verb can write (ADR 0005: every hard
   constraint sits downstream of a record the agent can change through a verb).
2. An inline filter in the transcript benchmark (`benchmark.md`) that `--fields` cannot remove.

Convenience never qualifies. The baseline transcripts held 119 inline Python filters: 14 were
hand edits of data files (now the `record` verb and the Drafts), 27 unwrapped an envelope after a
write, 25 projected fields, 5 discovered a schema, 15 stripped a stray `coach:` prefix the old CLI
printed before its JSON, and the rest asked the six questions the `query` views answer.

## The sixteen

| Leaf | Kind | Does |
| --- | --- | --- |
| `status` | read | where we stand and what needs attention; what the SessionStart hook shows |
| `schema [verb] [--registry <name>]` | read | the verb declarations as JSON Schema, or one registry as data |
| `import [--full]` | store write | Hevy workouts append-only with tombstones (ADR 0011); kit is a committed file, never imported (ADR 0021); like every verb, rebuilds a missing database from `export/` first (`schema.md`, "The rebuild") |
| `checkin open [--date <d>] [--tier light\|deep] [--readiness poor\|ok\|good]` | read | the check-in card (`check-in.md`) |
| `checkin record <draft>` | store write | the Check-in row plus every record the file carries |
| `record <draft>` | store write | ledger writes outside a check-in, any mix of record kinds |
| `plan draft [--week <monday>] [--out <path>]` | read, writes a Draft file | derives the week's Prescriptions, writes the plan Draft (with the window's Athlete notes as context), returns its path and summary |
| `plan apply <draft> [--dry-run] [--expect <hash>]` | Writing verb (Hevy) | the one Hevy write (ADR 0006, 0011) |
| `program show [--draft [--apply-plan <week>]]` | read, may write a Draft file | the version in force, or the current version as a Draft to edit |
| `program adopt <draft> [--dry-run] [--position <week>]` | store write | a new Program version (`program.md`) |
| `goal adopt <draft>` | store write | the Goal, and a Phase opened or closed in the same file (`goals.md`) |
| `progress` | read | the progress view (`goals.md`) |
| `query <view> [params]` | read | one of the six read views below |
| `publish [--dry-run]` | Writing verb (git) | export, pages, the athlete-authored files (`coach.toml`, `profile.md`, `kit/`), one commit (ADR 0001, 0012, 0021) |
| `upgrade [--dry-run]` | Writing verb (git) | migrate, export, bump the pin, regenerate, commit (ADR 0007) |
| `init [--dry-run] [--pin <X.Y.Z>]` | Writing verb (git) | create an instance (`instance.md`) |

Kinds: a **read** changes nothing (two reads write a Draft file, below). A **store write** changes
only the engine's own store and is allowed without a prompt. A **Writing verb** changes Hevy or
git and is asked (ADR 0006). The kind is one declaration field, `writes: none | store | hevy |
git`, and nothing else separates them: the permission rules ask on `hevy` and `git`, the hook
runs the dry run of a verb declared `hevy` or `git`, and `coach schema` prints the field. The
four asked verbs are the four Writing verbs: `plan apply` (`hevy`), `publish`, `upgrade` and
`init` (`git`). Every one declares `--dry-run`, which is what the hook's prompt shows: `plan
apply` the Hevy actions and the hash (ADR 0006), `publish` the files it would write, the
athlete-authored files it would commit and the export row counts per table, `upgrade` the migrations it would run and the files it would
regenerate, `init` the tree it would write. A dry run opens no transaction and touches no file.

Not leaves, and why:

- **`plan validate`**: `plan apply --dry-run` is the only check. It validates the Draft, diffs
  against the stored routine projection offline, and prints the Write plan hash. No second verb
  can disagree with the one that writes.
- **`explain`**: the plan Draft already carries evidence and constraints per line (ADR 0005);
  `--full` on a line and the `query` views cover the rest.
- **`sync`, `log add`, `niggle`, `followup`, `annotate`, `decide`, `observation`, `phase`**:
  `import` is the pull; everything the agent records between check-ins goes through `record`;
  Observations and Phases ride in the files that already carry the athlete's yes (ADR 0009,
  `goals.md`).
- **An exercise verb**: an Exercise edit is a record kind (below), not a verb and not a version.
- **A render verb**: pages are files `publish` writes (ADR 0012). No verb prints a page to stdout:
  `checkin open` returns the card as data the agent voices, `program show --draft` returns a form
  by path.

## Envelope and budget

The envelope is ADR 0002's: `schema_version`, `ok`, `verb`, `result` or `error {code, message}`,
`warnings[]`. Three rules every leaf obeys:

- **Stdout is exactly one JSON document.** Nothing before it, nothing after it, on any exit class.
  Diagnostics go to stderr. A contract test parses the stdout of every declared example as JSON.
- **3 KB default on every envelope.** Reads, write results, dry runs (the permission prompt shows
  one) and errors all fit it. Three verbs are allowed over it, because their whole default
  output is what the agent must act on: `checkin open` (the card), `plan apply --dry-run` (ADR
  0006's approval prompt) and `program adopt --dry-run` (every adopt warning). `--full` lifts the cap; `--fields a.b,c` is a comma list of dotted
  paths into `result`, allowed on every verb, and excludes `--full`. One generated size test per
  declaration.
- **Lists truncate, fields never drop.** A row list defaults to the newest 10 (`--last <n>`) and
  carries `count` and `truncated`; meeting the cap by truncating rows is allowed, meeting it by
  omitting a declared field is not.

## Drafts written by the engine

ADR 0002 has documents travel as files the agent wrote. Two reads hand the agent a form larger
than the cap, so they write it: `plan draft` and `program show --draft` write a TOML Draft
(through the one emitter in `render`, ADR 0019) to
`.coach/drafts/<date>-<kind>.toml` (or `--out <path>`) and return the path, the file hash and a
compact summary. The agent edits the file in place and passes the path to `plan apply` or
`program adopt`. The engine never overwrites a Draft. When the default path already exists and
its content equals what the verb would write (same hash), the verb returns `ok` with that path:
an identical re-derivation is a no-op. When the content differs, the verb writes to the next free
suffix, `<date>-<kind>-2.toml`, `-3`, and returns that path, so an edited Draft is never lost and
a re-draft on one day needs no flag. An explicit `--out` path that exists with different content
is exit 1, `error.code = draft_exists`, naming the path. The glossary's Draft entry is widened
accordingly.

### A Draft-local key

Ids are assigned inside the writing transaction (`schema.md`), so one file cannot cite a record
it raises by id. Any record table in a Draft may carry `key = "<word>"`, unique within the file,
and any ref in the same file may cite it as `<kind>:@<word>` (`evidence = ["niggle:@hamstring"]`,
an Annotation's target, a note's `about`). The writing service resolves every `@` ref to the
assigned id before it writes; the stored rows carry only real ids and the key is not stored. A
`@` ref with no matching key in the file is the violation `draft_ref_unresolved`
(`validation.md`). The same rule serves `checkin record`, `record` and `goal adopt`.

## Default summaries

What each leaf's `result` carries without `--fields` or `--full`. Row lists follow the list rule.

| Leaf | Default `result` |
| --- | --- |
| `status` | in order: engine version against the pin; Hevy on or off, age of the last import, workouts stored (Hevy and manual counts); store schema version; each plate-pool location's kit tables, current or stale against its inventory (`kit_tables_stale`, ADR 0021); plan in force (week, approved date, hash, routines verified or `unverified`); the rotation's week and position; program version in force; the current Goal (id, kind, priority lifts) and the open Phase (id, kind, `until`); Block (hard weeks against the ceiling, light week or deload pending); check-in due and its derived tier; open niggles and due follow-ups as counts with ids; Decisions in force as counts by kind with ids; current Observations as a count with ids; the outside-plan warnings standing (`validation.md`); whether the export is behind the store, or the store behind the export (`store_behind_export`, `schema.md`). No prose line. The cutover acceptance check reads this summary and nothing else (`cutover.md`) |
| `schema` | the declaration(s), or the registry rows |
| `import` | whether the store was rebuilt from the export first (`rebuilt`, with the manifest's schema version); workouts new, versioned, gone, back, window |
| `checkin open` | the card (`check-in.md`), derived tier, window; the outside-plan codes it reports in `warnings[]` (`week.md`) |
| `checkin record` | row id, window, tier, ids written by record kind, superseded row id if any. The file may carry `window_start` on the instance's first row only (`week.md`) |
| `record` | ids written by record kind, withdrawn or superseded ids if any |
| `plan draft` | path, hash, week, superseded plan id if any, line count, every violation and warning, rotation position and its source, `notes[]` (the Athlete notes since the last approved WeekPlan, verbatim with `about`; `check-in.md`) |
| `plan apply --dry-run` | ADR 0006's prompt summary: week, folders to create, routine changes (update, create, retire), templates to create, flags with acknowledgements, the hash |
| `plan apply` | WeekPlan id, hash, per-routine outcome (written, verified, unverified), audit lines appended |
| `program show` | version number, kind, emphasis, adopted date, `because`, sessions with line counts; with `--draft`: path and hash |
| `program adopt --dry-run` | the diff against the previous version with filled defaults, violations, warnings (`program.md`) |
| `program adopt` | version number, kind, Block reset or kept, acknowledgements frozen |
| `goal adopt` | goal id, kind, priority lifts, phase opened or closed |
| `progress` | `goals.md`'s view: per priority lift e1RM trend and cadence signal, milestones, Phase status, Block |
| `query` | `rows[]`, `count`, `truncated` |
| `publish` | commit hash, files written and deleted, export rows per table; with `--dry-run` the same with no commit hash |
| `upgrade`, `init` | ADR 0007 and `instance.md`; with `--dry-run`, the migrations and files `upgrade` would touch, the tree `init` would write |

## Arguments with rules

- **`checkin open --tier`** only raises the derived tier to `deep`; it never lowers it, and it is
  honoured on a catch-up (`week.md`, `check-in.md`).
- **`plan draft --week`** defaults to the next week with no approved plan, or the current week
  while its plan is unapproved. When an approved WeekPlan exists for the week, the Draft is a
  superseding one and the summary names the plan it supersedes.
- **`import`** has one source, Hevy; with no `[hevy]` table it reports `skipped` and exits 0.
  Kit is read from `kit/` by the verbs that round, never pulled (ADR 0021).
- **`program show --apply-plan <week>`** folds that WeekPlan's swap and pin overrides into the
  Draft (`program.md`; the kinds and what each folds to are `overrides.md`'s).
- **`schema --registry`** takes the name of any registry a `schema.md` CHECK list or a Draft
  parser is tested against: `schemes`, `flags`, `record-kinds`, `views`, `decision-kinds`,
  `override-kinds`, `reasons` (the seven `because` values), `annotation-kinds`,
  `constraint-kinds`, `set-types`, `load-modes`, `equipment-kinds`. It is the one source every
  contract test reads a registry from. `flags` carries each code's `rn` citation, the one place
  a new agent sees every code with its evidence (ADR 0020).
- **`init --pin`** is required on a `.dev` build of the engine: `init` refuses (exit 5,
  `engine_pin_required`) rather than write a `.dev` pin into `coach.toml`, since only `upgrade`
  rewrites `[engine]` and `engine_pin_dev` would otherwise never clear (ADR 0007). On a release
  build the pin is the engine's own version and `--pin` is refused if it differs.

## Record kinds

A **record kind** is one typed table a ledger Draft may carry. One registry serves both
`checkin record` and `record`: the file is TOML, one array of tables per kind, any mix. The
check-in file adds its own header (`date`, `tier`, `read`; `check-in.md`).

| Kind | Table | Writes | Reserved to the check-in |
| --- | --- | --- | --- |
| niggle | `[[niggle]]` | a Niggle status event, with its load constraint and rehab session link (ADR 0010) | |
| followup | `[[followup]]` | a Follow-up event: deferred, kept, resolved, dropped | |
| decision | `[[decision]]` | a Decision of any of the ten kinds in `overrides.md` (`override`, `park_session`, `resume_session`, `leave_warning`, `training_max`, `safety_ceiling`, `activity_cap`, `decline_ceiling`, `defer_deep_review`, `against_research`), or a `retire` of one | |
| annotation | `[[annotation]]` | an Annotation, or the withdrawal of one | |
| note | `[[note]]` | an Athlete note with its optional `about` ref | |
| workout | `[[workout]]` | a workout Hevy never saw: Hevy off (ADR 0006, `instance.md`), or a session the athlete reports and did not log (`cutover.md`); never sent to Hevy | |
| weigh_in | `[[weigh_in]]` | a Weigh-in | |
| sleep_night | `[[sleep_night]]` | a Sleep night | |
| activity | `[[activity]]` | an Activity | |
| status_span | `[[status_span]]` | a Status span: ill, injured, travel, `no_training`; withdrawn, never deleted | |
| exercise | `[[exercise]]` | an edit to an existing library Exercise (the four Hevy template columns, load mode, equipment kind; name and identity stay), or a new library Exercise with every column, `source = record`, for a Hevy template the history uses and no program line names (`cutover.md`) | |
| observation | `[[observation]]` | an Observation raised or retired (ADR 0009) | yes |

A reserved kind in a plain `record` file is the violation `record_kind_not_allowed`. A Phase is
opened or closed inside a check-in file or a `goal adopt` Draft (`goals.md`), so it is not a
`record` kind.

## Read views

Six parametrised reads under `query`, each within the cap, each a row list:

| View | Params | Rows |
| --- | --- | --- |
| `exposures` | `--exercise <id>` (repeatable), `--since <date>` or `--last <n>` | date, session, load, reps, RPE, e1RM, annotations applied |
| `readings` | `--kind weigh_in\|sleep_night\|activity`, `--last <n>` | the record's fields with source |
| `flags` | `--code`, `--severity`, `--scope`, `--summary`, `--draft <path>` | flags frozen on the plan in force, or, with `--draft`, on that plan Draft re-validated now (the same validation `plan apply --dry-run` runs, read-only); `--summary` gives counts by (code, severity) |
| `lines` | `--exercise`, `--session`, `--date`, `--changed`, `--draft <path>` | lines of the plan in force, or of the named Draft: date, session, exercise, prescription, change from last week, flags |
| `routines` | none | the Routine map joined to folders: session, routine id, folder, status, last verified |
| `ledger` | `--kind <record kind>`, `--id <id>`, `--open` | the record's fields and its event history |

Field projection is `--fields`, never a view. No verb knows a "current" Draft: a Draft is read by
nothing after its verb consumes it (`instance.md`), so a read either names the file by path or
reads the plan in force.

## Re-run safety

Every verb does a whole job and is safe to run twice (review principle 3).

**Same Draft, same answer.** Every verb that takes a Draft hashes the file and stores the hash
with what it wrote. A second call with an identical hash finds those rows and returns them with
`ok` and the same ids, writing nothing. A differing hash does what the record's spec says:

| Leaf | Identical hash | Different hash, same subject |
| --- | --- | --- |
| `checkin record` | no-op, same row id | the new row supersedes the earlier one for that date (`check-in.md`) |
| `record` | no-op, same ids | appends new rows; a withdrawing annotation or later event supersedes as its spec says |
| `program adopt` | no-op, same version number | a new version; a redesign resets the Block once per version, never per call |
| `goal adopt` | no-op, same goal id | a new Goal row; the earlier is superseded |
| `plan apply` | resumes: re-PUTs only `unverified` routines and those whose stored projection differs, verifies, and is a no-op `ok` once all are verified (ADR 0006, 0011) | exit 3, `--expect` mismatch; nothing sent |

Verbs without a Draft:

| Leaf | Second call |
| --- | --- |
| `import` | no new versions, no-op counts of zero |
| `publish` | nothing to export and no page changed: no commit, `ok` |
| `plan draft`, `program show --draft` | `ok` with the same path when the file equals what it would write; the next `-n` suffix when it differs (above) |
| `upgrade` | pin already at the engine version: no-op |
| `init` | an instance already exists: exit 5, `instance_exists` |
| reads | pure |

`plan apply` after a partial failure: the WeekPlan row is approved and frozen before the first
Hevy call (approval survives a failed push, ADR 0006), each routine is PUT, read back and marked
`active` or left `unverified`; the client writes the audit's request line before each send and
its response line when the attempt ends (ADR 0011), so a request with no response line marks
where a process died. The re-run with the same `--expect` prompts again and resumes from the
Routine map's statuses. If a routine the Write plan touches changed in the mirror after approval,
other than by this push's own read-back, the dry run prints a new hash covering the changed
versions, and the re-run refuses `expect_mismatch` until that hash is approved.

## Exit classes

| Class | When |
| --- | --- |
| 0 | ok, including every no-op above |
| 1 | a Draft with any violation on `plan apply --dry-run`, `program adopt`, `checkin record`, `record`, `goal adopt`; `draft_exists` on an explicit `--out`; an unknown view or record kind; a routine read-back that differs (`verify_failed`, ADR 0011); malformed input: an unknown or ill-typed argument, a Draft field that does not parse, an id in the wrong form, a file argument that cannot be read (`invalid_argument`); well-formed input that stored state or a rule forbids, the message naming the rule and the fact (`state_conflict`); a goal naming a priority lift twice (`priority_lift_duplicate`) or a milestone with no target (`milestone_target_missing`); a `[phase]` opening while another is open (`phase_already_open`) |
| 3 | a guard refuses a write: `plan apply` without `--expect` (`expect_missing`), with a changed hash (`expect_mismatch`), with a routine moved in Hevy since the import (`routine_moved`, ADR 0011), with two Hevy folders sharing the title of a folder it must adopt (`folder_title_shared`, ADR 0011), or when the write audit cannot be opened for append (`audit_unwritable`, ADR 0011). Whether a permission mode allows the prompt is the hook's answer, never the verb's |
| 4 | Hevy unreachable or answering with a payload the client cannot read, on `import` and `plan apply` (`hevy_unreachable`) |
| 5 | setup stops it: `init` on an instance (`instance_exists`), `init` on a `.dev` build without `--pin` (`engine_pin_required`), `init` where git is not on the PATH (`git_unavailable`) or knows no committer (`git_identity_missing`), both before a file is written, `init` where a `.env` already exists (`env_file_exists`), before a file is written; `upgrade` on a git tree with uncommitted changes (`git_tree_dirty`), or git refuses the commit (`git_commit_failed`, naming the command that finishes it), or another git step fails (`git_failed`), a pin mismatch (`engine_pin_mismatch`), outside an instance (`no_instance`), a schema behind the engine (`schema_behind`), a `[hevy]` table with no key in the environment or `.env` (`hevy_key_missing`, on `import` and `plan apply`), an unknown table or key in `coach.toml`, or an `implements` value naming no implement of its location (`config_unknown_key`, on every verb; `instance.md`), a plate-pool location whose `kit/<name>.achievable.json` is missing or carries an `inventory_sha256` other than the hash of `kit/<name>.json` (`kit_tables_stale`, naming the location and the generator command, on `plan draft` and `program adopt`; ADR 0021); on the rebuild, `export_newer_than_engine`, or an export row that does not parse (`jsonl_row_malformed`); on any store write, `store_behind_export` (`schema.md`, "The rebuild") |

`error.code` carries the flag code or the refusal reason named above. Nothing else refuses. A
refusal reason is not a flag: it has no scope, no registry row and no `rn`.

## Contract tests

Generated from the declarations, none hand-written per verb:

- Sixteen leaves exist and no more; every leaf a skill names exists (`skills.md`). `coach-hook`
  is a separate console entry point for the plugin's hooks (ADR 0019), not a leaf, and is absent
  from `--help`, `schema` and the generated permission rules.
- Every declared example's stdout parses as exactly one JSON document.
- Every default envelope but the three allowed over it is under 3 KB on the fixture instance,
  which overflows every list a default summary truncates (`testing.md`); this test lives in
  `tests/contract/` only.
- Every verb declared `writes: hevy` or `git` declares `--dry-run`, and its dry run on the
  fixture instance writes no file and opens no transaction.
- Every violation code's clearing verb or record exists (`validation.md`).
- The registries `schema --registry` prints are the ones the validator, the record parser and
  `query` dispatch on.

## Hand-offs

- **Override catalogue** (#19, settled in `overrides.md`): the Decision kinds `[[decision]]` accepts; the override kinds
  `--apply-plan` folds in.
- **Schema** (settled in `schema.md`): the `draft_hash` column on every row a Draft verb writes;
  the record-kind and view registries stay in code and `schema --registry` is how a contract
  test reads them.
- **Skills**: the four skills name only these leaves; `check-in` names `status`, `checkin open`,
  `checkin record` and `query` (`skills.md`'s worked example is the list).
