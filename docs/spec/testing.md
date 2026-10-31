# Testing: fixtures, the fake Hevy, and what the suite proves before cutover

Resolves wayfinder #33. Wayfinder #34 extends this document with the module seams, the test
pyramid, the runner and the wall-time budget.

## What the suite is for

The suite proves the engine's own behaviour. It never compares the engine with the old
instance: no recorded old outputs, no replay of old sessions, nothing in CI or in the engine
that knows the old system existed. One-off comparisons during development are fine as scratch
work and are never committed.

Tests assert behaviour on values. No test reads a spec document, an ADR, the glossary, a skill
body or any other prose to decide pass or fail. A test may name the spec section or ADR that
owns the rule in a comment, so a reader can find the reasoning; it never parses it.

`docs/spec/parity.md` is the 2026-10-26 review of the old system's behaviours. It is reference,
not a test source: later decisions changed or dropped many of its rows, and where they differ
the spec documents and ADRs win. No test cites a parity row.

## Fixtures

Most tests build their own history with scenario builders: small Python functions
(`a_program_with(...)`, `exposures_for(line, weeks=...)`, `a_niggle(...)`) that insert rows into
an in-memory SQLite database created from `schema.sql`. Each test states exactly the history it
needs and nothing else. No real athlete data enters the engine repository.

Two committed fixture directories cover what builders cannot:

- `tests/fixtures/instance/`: one complete synthetic **Fixture instance**, laid out as `coach
  init` would write it (`coach.toml`, `profile.md`, `export/` with its manifest). Used by the
  import, export round-trip and CLI envelope tests, and by the size test that holds every
  default envelope under 3 KB (`verbs.md`). It is small and hand-authored.
- `tests/fixtures/hevy/`: a handful of anonymised Hevy GET responses (a workout page, a routine,
  a folder, an exercise template). They fix the payload shapes the parser must accept and feed
  the parser tests only.

## The fake Hevy

Hevy is tested against one in-process fake client, `FakeHevy`, holding routines, folders,
templates and workouts in memory. It implements exactly the allow-listed endpoints (ADR 0011)
and raises on everything else, so a test that reaches a forbidden endpoint fails by
construction. A test can tell it to move a routine's `updated_at`, fail the next GET, return a
read-back that differs from the PUT, or answer 429. No HTTP, no cassette files, no network in
the suite.

## The cutover Draft

The cutover check-in Draft (`cutover.md`, "The cutover check-in") holds the athlete's real
niggles, observations, goal and phase. It is not an engine test. The suite runs a synthetic
ledger Draft of the same shape through `checkin record` and asserts the resulting status: open
niggles each with a constraint, observations current, one Goal and one open Phase, manual
workouts present, one `activity_cap` in force. The real Draft is run once by hand against a
scratch instance during the last old week, and the acceptance numbers in `cutover.md` are
checked by eye.

## The benchmark

`benchmark.md` measures a real transcript, so it cannot run in CI and is never a gate. Its pass
bar is the three targets already written there: under 10 coach calls, under 8k instruction
tokens and zero inline Python per check-in plus programming pass. It is measured on the first
two real weekly passes after cutover and at each later milestone, each as a dated row in the
table. A miss opens an issue. Cutover is gated by the green suite at the pinned engine tag and
the acceptance check, nothing else.
