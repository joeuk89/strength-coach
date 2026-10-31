# Verb set and output budgets

The sixteen verbs the agent, the hooks and a human terminal can run, what each returns by
default, what a second identical call does, and the rule for adding one. Decided 2026-10-31
(wayfinder #16). The architecture they sit on is ADR 0002: a CLI over plain service functions,
one JSON envelope per call, one declaration per verb generating `--help`, `schema` and the
contract tests.

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
| `import [--full] [--only hevy\|kit]` | store write | Hevy workouts append-only with tombstones (ADR 0011) and the plate-pool snapshot (ADR 0008) |
| `checkin open [--date <d>] [--tier light\|deep]` | read | the check-in card (`check-in.md`) |
| `checkin record <draft>` | store write | the Check-in row plus every record the file carries |
| `record <draft>` | store write | ledger writes outside a check-in, any mix of record kinds |
| `plan draft [--week <monday>] [--out <path>]` | read, writes a Draft file | derives the week's Prescriptions, writes the plan Draft, returns its path and summary |
| `plan apply <draft> [--dry-run] [--expect <hash>]` | Writing verb (Hevy) | the one Hevy write (ADR 0006, 0011) |
| `program show [--draft [--apply-plan <week>]]` | read, may write a Draft file | the version in force, or the current version as a Draft to edit |
| `program adopt <draft> [--dry-run] [--position <week>]` | store write | a new Program version (`program.md`) |
| `goal adopt <draft>` | store write | the Goal, and a Phase opened or closed in the same file (`goals.md`) |
| `progress` | read | the progress view (`goals.md`) |
| `query <view> [params]` | read | one of the six read views below |
| `publish` | Writing verb (git) | export, pages, one commit (ADR 0001, 0012) |
| `upgrade` | asked verb | migrate, export, bump the pin, regenerate, commit (ADR 0007) |
| `init` | asked verb | create an instance (`instance.md`) |

Kinds: a **read** changes nothing. A **store write** changes only the engine's own store and is
allowed without a prompt. A **Writing verb** changes Hevy or git and is asked (ADR 0006). The
four asked verbs are `plan apply`, `publish`, `upgrade` and `init`.

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
  one) and errors all fit it. `--full` lifts the cap; `--fields a.b,c` is a comma list of dotted
  paths into `result`, allowed on every verb, and excludes `--full`. One generated size test per
  declaration.
- **Lists truncate, fields never drop.** A row list defaults to the newest 10 (`--last <n>`) and
  carries `count` and `truncated`; meeting the cap by truncating rows is allowed, meeting it by
  omitting a declared field is not.

## Drafts written by the engine

ADR 0002 has documents travel as files the agent wrote. Two reads hand the agent a form larger
than the cap, so they write it: `plan draft` and `program show --draft` write a TOML Draft to
`.coach/drafts/<date>-<kind>.toml` (or `--out <path>`) and return the path, the file hash and a
compact summary. The agent edits the file in place and passes the path to `plan apply` or
`program adopt`. If the target path already exists the verb refuses with exit 1 and
`error.code = draft_exists`, naming the path, so an edited Draft is never overwritten; `--out`
picks another. The glossary's Draft entry is widened accordingly.

## Default summaries

What each leaf's `result` carries without `--fields` or `--full`. Row lists follow the list rule.

| Leaf | Default `result` |
| --- | --- |
| `status` | in order: engine version against the pin; Hevy on or off, age of the last import and of the kit snapshot; plan in force (week, approved date, hash, routines verified or `unverified`); Block (hard weeks against the ceiling, light week or deload pending); check-in due and its derived tier; open niggles and due follow-ups as counts with ids; the outside-plan warnings standing (`validation.md`); whether the export is behind the store. No prose line |
| `schema` | the declaration(s), or the registry rows |
| `import` | per source: ran or skipped and why; Hevy: workouts new, versioned, tombstoned, window; kit: snapshot date and whether it changed |
| `checkin open` | the card (`check-in.md`), derived tier, window |
| `checkin record` | row id, window, tier, ids written by record kind, superseded row id if any |
| `record` | ids written by record kind, withdrawn or superseded ids if any |
| `plan draft` | path, hash, week, superseded plan id if any, line count, every violation and warning, rotation position and its source |
| `plan apply --dry-run` | ADR 0006's prompt summary: week, routine changes (update, create, retire), templates to create, flags with acknowledgements, the hash |
| `plan apply` | WeekPlan id, hash, per-routine outcome (written, verified, unverified), audit lines appended |
| `program show` | version number, kind, emphasis, adopted date, `because`, sessions with line counts; with `--draft`: path and hash |
| `program adopt --dry-run` | the diff against the previous version with filled defaults, violations, warnings (`program.md`) |
| `program adopt` | version number, kind, Block reset or kept, acknowledgements frozen |
| `goal adopt` | goal id, kind, priority lifts, phase opened or closed |
| `progress` | `goals.md`'s view: per priority lift e1RM trend and cadence signal, milestones, Phase status, Block |
| `query` | `rows[]`, `count`, `truncated` |
| `publish` | commit hash, files written and deleted, export rows |
| `upgrade`, `init` | ADR 0007 and `instance.md` |

## Arguments with rules

- **`checkin open --tier`** only raises the derived tier to `deep`; it never lowers it.
- **`plan draft --week`** defaults to the next week with no approved plan, or the current week
  while its plan is unapproved. When an approved WeekPlan exists for the week, the Draft is a
  superseding one and the summary names the plan it supersedes.
- **`import --only`** picks one source. Without it both run, each as its own transaction: Hevy
  unreachable still stores the kit snapshot and exits 4 with that result reported; Hevy off pulls
  the kit only and says so.
- **`program show --apply-plan <week>`** folds that WeekPlan's swap and pin overrides into the
  Draft (`program.md`; the kinds and what each folds to are `overrides.md`'s).
- **`schema --registry`** takes `schemes`, `flags`, `record-kinds` or `views`. It is the one
  source every contract test reads a registry from. `flags` carries each code's `rn` citation,
  the one place a new agent sees every code with its evidence (ADR 0020).

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
| workout | `[[workout]]` | a workout Hevy never saw: Hevy off (ADR 0004), or a session the athlete reports and did not log (`cutover.md`); never sent to Hevy | |
| weigh_in | `[[weigh_in]]` | a Weigh-in | |
| sleep_night | `[[sleep_night]]` | a Sleep night | |
| activity | `[[activity]]` | an Activity | |
| status_day | `[[status_day]]` | a status day span: ill, injured, travel, `no_training`; withdrawn, never deleted | |
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
| `readings` | `--kind weigh_in\|sleep\|activity`, `--last <n>` | the record's fields with source |
| `flags` | `--code`, `--severity`, `--scope`, `--summary` | flags on the current Draft or the plan in force; `--summary` gives counts by (code, severity) |
| `lines` | `--exercise`, `--session`, `--date`, `--changed` | lines of the current Draft or the plan in force: date, session, exercise, prescription, change from last week, flags |
| `routines` | none | the Routine map joined to folders: session, routine id, folder, status, last verified |
| `ledger` | `--kind <record kind>`, `--id <id>`, `--open` | the record's fields and its event history |

Field projection is `--fields`, never a view.

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
| `plan draft`, `program show --draft` | exit 1 `draft_exists` on the same path |
| `upgrade` | pin already at the engine version: no-op |
| `init` | an instance already exists: exit 5 |
| reads | pure |

`plan apply` after a partial failure: the WeekPlan row is approved and frozen before the first
Hevy call (approval survives a failed push, ADR 0006), each routine is PUT, read back and marked
`active` or left `unverified`, and the audit line is appended before the response is parsed. The
re-run with the same `--expect` prompts again and resumes from the Routine map's statuses.

## Exit classes

| Class | When |
| --- | --- |
| 0 | ok, including every no-op above |
| 1 | a Draft with any violation on `plan apply --dry-run`, `program adopt`, `checkin record`, `record`, `goal adopt`; `draft_exists`; an unknown view or record kind |
| 3 | `plan apply` without `--expect`, with a changed hash, or under bypass permissions |
| 4 | Hevy unreachable, on `import` and `plan apply` |
| 5 | `init` on an instance, a pin mismatch, a missing Hevy key with Hevy on |

`error.code` carries the flag code or the refusal reason. Nothing else refuses.

## Contract tests

Generated from the declarations, none hand-written per verb:

- Sixteen leaves exist and no more; every leaf a skill names exists (`skills.md`). `coach-hook`
  is a separate console entry point for the plugin's hooks (ADR 0019), not a leaf, and is absent
  from `--help`, `schema` and the generated permission rules.
- Every declared example's stdout parses as exactly one JSON document.
- Every default envelope is under 3 KB on the fixture instance.
- Every violation code's clearing verb or record exists (`validation.md`).
- The registries `schema --registry` prints are the ones the validator, the record parser and
  `query` dispatch on.

## Hand-offs

- **Override catalogue** (#19, settled in `overrides.md`): the Decision kinds `[[decision]]` accepts; the override kinds
  `--apply-plan` folds in.
- **Schema**: the `draft_hash` column on every row a Draft verb writes; the record-kind and view
  registries as tables the contract tests read.
- **Skills**: the four skills name only these leaves; `check-in` names `status`, `checkin open`,
  `checkin record`, `record`, `query`.
