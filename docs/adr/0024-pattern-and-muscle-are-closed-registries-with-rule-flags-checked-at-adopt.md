---
status: accepted
date: 2026-11-07
---

# Pattern and muscle are closed registries whose entries carry the rule flags, checked at adopt and not in the DDL

An Exercise's `pattern` and the names in its `muscles` table are closed sets, declared in code
as registries beside load modes and equipment kinds and shown under `coach schema --registry`.
A pattern entry carries `heavy` and `compound`; a muscle entry carries `dosed`. The rules that
used to keep their own hand-written lists of names (the heavy-pattern list behind the next-day
activity rule, the compound list behind RPE drift, the dosed-muscle list behind the dose rule)
read those flags instead. `adopt` refuses a Draft that names a pattern or muscle outside its
registry (`unknown_pattern`, `unknown_muscle`), on library rows, Draft-declared exercises and
`estimated_sets` keys alike. The pattern set gains `balance`; the muscle set loses `cardio` and
`full_body`. The DDL does not change. Spec: `docs/spec/program.md`, `schema.md`; issue #257.

## Context

`pattern` was free text and `muscles` was checked for shape only, yet four rules keyed on exact
names: the heavy-pattern list, the compound list, the `counted_variant_off_pattern` flag and
`avoid` niggle constraints that name a pattern. A misspelled or novel name passed `adopt` and
silently fell out of every rule. The catalogue used 18 patterns and 20 muscle names, of which
two (`cardio`, `full_body`) are not muscles and seven are never asked for by name. Nothing told
an agent which names were in use or whether a new one was allowed, so a balance exercise was
filed under `core`, where its sets would have counted toward `abdominals` dose.

## Considered options

- **Closed registries with rule flags on the entries, errors at adopt, no DDL CHECK (chosen).**
  One source of truth per set; the rules derive their lists from the flags; the agent reads the
  flags from the registry rows. The guard is the adopt check at the door plus a contract test
  that the catalogue is a subset of each registry, the same two guards for both fields.
- **Free text kept, a warning at adopt for a name not yet seen.** Rejected: a warning lets the
  heavy-pattern and dose rules run on a hole, and "seen before" is not a definition.
- **A `CHECK (pattern IN (...))` in the DDL, as load mode has.** Rejected: a schema migration
  for every instance, and `muscles` is a JSON column a CHECK cannot read, so the two fields
  would have ended up with different guards.
- **Parallel lists kept beside the registries.** Rejected: `DOSED_MUSCLES`, the heavy list and
  the compound list are each a view of one fact about an entry, and a second list drifts.
- **`stability` instead of `balance`.** Rejected: `stability` would also claim anti-rotation
  work, which lives under `core` and doses `abdominals`; `balance` is what the athlete, the
  research note and ADR 0023's example call it, and it joins no rule list.
- **`cardio` and `full_body` kept as undosed muscle entries.** Rejected: a muscle registry that
  contains `cardio` is lying about its name; the `conditioning` pattern already says what that
  work is, and an empty muscle table is legal.

## Consequences

- The glossary gains Pattern and Muscle and the Exercise entry drops "movement pattern".
- The registries `patterns` and `muscles` appear under `coach schema --registry`, pattern rows
  with `heavy` and `compound`, muscle rows with `dosed`.
- The error catalogue gains `unknown_pattern` and `unknown_muscle`, raised beside
  `unknown_load_mode`.
- The seven conditioning catalogue rows carry `{primary = [], secondary = []}`. Instance-added
  rows outside the sets are not migrated: the next adopt that references one raises the error
  and the agent fixes the row through the normal path.
- A contract test asserts every catalogue pattern and muscle is in its registry.
