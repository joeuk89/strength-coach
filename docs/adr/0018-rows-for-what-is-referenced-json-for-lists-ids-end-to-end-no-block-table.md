---
status: accepted
date: 2026-10-31
---

# Rows for what is referenced, JSON for lists; one id form end to end; typed text refs; the Block is derived

The store's shape follows one rule: anything another row refers to by id, or a `query` view
filters on, is a row with a real key and foreign keys; ordered lists (set groups, rotation
weeks, derivation steps) and the params of a scheme, an override or a Decision are JSON text
columns on that row. Every row that is referred to carries an engine-assigned prefixed text id
(`d-0001`, `wp-2026-11-02`, `pv-3`) that is the same string in the envelope, in evidence refs
and in the export. A column that may point at more than one table holds a typed text ref,
`kind:id`, validated by the writing service. The Block has no table: its boundaries are the
`redesign` adoptions and the check-ins whose closed week kind resets the count, and its id is
its opening date. Spec: `docs/spec/schema.md`.

## Context

ADR 0001 chose SQLite for cross-record transactions and integrity by schema, and every later
decision added records without saying how they sit in tables. The program version is one
authored document (ADR 0015) with sessions and lines inside it; the WeekPlan carries overrides,
acknowledgements and frozen prescriptions (ADR 0003, 0016); the ledger has a dozen record
kinds (`verbs.md`), several with event histories. Three choices decide how much of ADR 0001's
integrity the schema keeps.

## Considered options

- **Rows for referenced things, JSON for lists and params (chosen).** The Routine map, a park
  Decision and a prescription all point at a session; a `lines` view filters on exercise; so
  sessions and lines are rows under a `session` identity table that outlives any version. Set
  groups and scheme params are read whole by `prescribe` and never filtered, so they stay JSON.
- **The version and the plan as JSON documents on one row each.** Loses every foreign key from
  the ledger into the program, which is what SQLite was chosen for; integrity returns to code.
- **Full normalisation down to the set group and the param.** Tables nothing queries, and a
  scheme's params would need a table per scheme.
- **Integer rowids with a display id derived at the edge.** Two id forms, a mapping at every
  verb boundary, and an export whose ids change on re-import.
- **One nullable foreign-key column per target kind on every referencing table.** SQLite has
  no polymorphic key; a note's `about` would be four columns and a CHECK. The typed ref costs
  one validation at write time and reads the same everywhere a flag scope already does.
- **A `block` table written by `checkin record`.** Stores a derived week kind, the second
  source of truth ADR 0016 refused when it ruled out a block reset Decision.

## Consequences

- 36 tables, in `docs/spec/schema.md` as DDL that the engine's `schema.sql` matches byte for
  byte. No table for Block, planned session, Exposure, Match, Miss, e1RM or progression state.
- Rows are immutable and a correction is a new row, with four named in-place exceptions
  (`exercise`, `observation`, `phase`, `routine_map`), each with its audit stated.
- A rehab session is a `rehab_session` row under its niggle with its lines as JSON, never a
  version row; `lines` unions it in.
- Decision `session_id` and `exercise_id` are columns, not params, because the supersede rule
  keys on them; every other param stays JSON.
- Partial unique indexes carry the one-at-a-time rules: one approved plan per week, one current
  Goal, one open Phase, one override per kind per scope.
- ADR 0009 and 0010 are read with park and resume as their own Decision kinds, not override
  Decisions with no until date (`overrides.md` is the catalogue).
