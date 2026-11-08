---
status: accepted
date: 2026-10-26
amended: 2026-10-31 by wayfinder #46 (`coach.toml`, no recipe cards or proposals); 2026-10-31 by wayfinder #42 (the rebuild from the export runs only when the database file is missing, never on an export "older than a commit"; each migration freezes the DDL it leaves behind, `docs/spec/schema.md`); 2026-11-08 by the review of PR #271 (every schema change is a migration, cutover or not; the chain started with `m0001` during build v6)
---

# SQLite is the source of truth; git sees only a text export

The old system held the truth in about 20 overlapping JSON files with hand-written integrity
checks and no transaction across files. The engine stores everything that is not authored prose
in one SQLite database (Python stdlib), gitignored in the instance at `.coach/coach.db`. Git sees
a deterministic export, sorted JSONL per table, written by `publish` after approval; the store
rebuilds the database from it, by itself, in exactly one case: the database file is missing
(amended 2026-10-31; with a database present the export is never read, so a rebuild can never
discard a row the store has). SQLite won on cross-record transactions and rows made immutable by schema,
which no file layout gets for free, and on SQL views giving the agent its 1–3 KB summaries.

## Considered options

Scored against the athlete's weights (integrity 25, simplicity 20, audit 20, migration 15,
testability 10, portability 10), after a red-team pass that corrected three advocate claims: the
old `status` is slow because of its schema validator and page re-rendering, not file scans;
foreign keys replace about 7 checks, not 15; per-file atomic writes already existed.

- **SQLite + export with auto-import (chosen): 82.**
- **Single-file JSON store, one atomic replace: 74.5.** Atomic, 6 ms to parse, but integrity stays
  in code. Wins if the athlete ever edits stored data by hand as a habit.
- **Files as truth loaded into in-memory SQLite: 72.5.** Constraints and views without a binary
  file, at the cost of a bespoke write path, a load per verb, and a post-crash state that refuses
  to load.
- **One file per table: 69.5.** The old shape, consolidated.
- **SQLite binary committed: rejected.** Binary diffs are no audit trail.
- **Event log plus snapshot: not scored.** Its two benefits are taken piecemeal below.

## Consequences

- `PRAGMA foreign_keys = ON` is set in the single connection factory and covered by a test; it
  defaults to off per connection.
- The Hevy write audit is an append-only committed file written at request time, never only a
  database row: a session abandoned between a Hevy push and `publish` must still leave a record.
- Workout import is append-only with tombstones; approval binds to an immutable plan row, not a
  hash over a mutable file.
- The export is output. No code reads it except `import`; the athlete never edits it.
- Files stay files when they are authored prose: `coach.toml`, `profile.md`, `.env`, the kit
  files, research notes in the engine repo. The store never caches a copy of `coach.toml`.
- Stored data is never edited by hand. The exception is the program, which is authored: an
  `adopt` verb validates a text form and records it as a new program version.
- Git sees one commit per `publish`; Drafts never reach git (`.coach/drafts/` is gitignored).
- A schema change is one linear `user_version` migration over one frozen DDL per schema version,
  so a rebuild can build an export at any version it was written at. Adding a UNIQUE constraint or changing a CHECK
  needs a table rebuild in SQLite.
- A second machine clones the instance and runs the engine; the missing database is rebuilt
  from the export on the first verb. To take a newer export later, delete the database file.
