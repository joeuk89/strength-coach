# Testing: fixtures, the fake Hevy, and what the suite proves before cutover

Resolves wayfinder #33 (fixtures, the fake Hevy, what the suite proves) and #34 (module seams,
the test pyramid, the runner and the wall-time budget; ADR 0019).

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

## Package layout

One repo is the package and the plugin (ADR 0007). `pyproject.toml` at the root declares the
`coach` package under `src/`, two console scripts (`coach` and `coach-hook`), no runtime
dependencies, a Python 3.12 floor, and a `dev` dependency group holding pytest, ruff and
pyright. `uv tool install --editable .` is the development install.

```
pyproject.toml
src/coach/
  __main__.py          python3 -m coach
  core/                pure functions, frozen values, the code registries
  store/               schema.sql, connection factory, migrations, reads and writes
  hevy/                HevyClient protocol, the allow-listed client, payload parsing
  kit.py               plate-pool snapshot fetch and parse
  render/              pages and Drafts as text
  services/            one module per verb leaf
  cli/                 declarations, argv, envelope, exit codes, root, .env, git, hooks
tests/
  core/  services/  cli/  contract/
  fixtures/instance/  fixtures/hevy/
  support/             scenario builders, FakeHevy, fixed clock
.claude-plugin/  skills/  hooks/
```

The split inside each package, the builder and fixture names and the CI file are the first
build ticket's calls.

## Module seams

Six packages, one import direction (ADR 0019):

| Package | Owns | May import |
| --- | --- | --- |
| `core` | schemes, e1RM, return bands, week kind, units, loads and rounding, the eight-step `prescribe` pipeline (ADR 0017), validation rules, the registries (`schemes`, `flags`, `record-kinds`, `views`) | stdlib, `core` |
| `store` | `schema.sql` (byte-identical to `schema.md`), the connection factory with `foreign_keys` on, migrations, functions that read rows into `core` values and write values as rows | `core` |
| `hevy` | the `HevyClient` protocol, the real client over `urllib`, payload parsing from the fixture shapes | `core` |
| `render` | `pages/*` and the plan and program Drafts, as text from `core` values | `core` |
| `services` | one function per leaf: load a snapshot through `store`, run `core`, write in one transaction, return a typed result or raise `Refused`, `Invalid`, `Unreachable` or `Setup` | `core`, `store`, `hevy`, `render` |
| `cli` | verb declarations, argv parsing, the envelope, exit-code mapping, instance-root discovery, `.env`, git, filesystem, the `coach-hook` commands | everything |

`core` never imports `sqlite3`, `urllib`, `os`, `pathlib`, `subprocess` or reads the current
time; dates arrive as values. `render` never imports `store`. A contract test walks every module
with `ast` and fails on any other edge.

Three things are injected, because each has two adapters:

- **The store**: a bare `sqlite3.Connection`, a file in the instance or `:memory:` in a test. No
  repository interface; `store` is a module of functions and the service chooses the
  transaction boundary.
- **Hevy**: `HevyClient`, a `typing.Protocol` of the four allow-listed writes (ADR 0011) and the
  GETs. `hevy/client.py` and `tests/support/fake_hevy.py` both satisfy it.
- **The clock**: `Clock`, a protocol with `today()` and `now()`. Services take it; `cli` passes
  the system clock; the Hevy audit's timestamps come from it.

## The test pyramid

Four layers, mirrored in `tests/`:

| Layer | Runs against | Covers |
| --- | --- | --- |
| `tests/core/` | values only, no database | schemes, the pipeline, bands, rounding, validation, registries; the bulk of the suite |
| `tests/services/` | `:memory:` built from `schema.sql` through scenario builders, `FakeHevy`, a fixed clock | each leaf's behaviour, transactions, refusals, idempotent re-runs |
| `tests/cli/` | in-process `main(argv, env, stdout, stderr)`; the fixture instance | one test per exit class, `init`, `import`, the export round-trip, the 3 KB envelope size test; one subprocess smoke test that the installed `coach --help` runs |
| `tests/contract/` | the declarations, `schema.sql`, the registries, the skill files, the source tree | the generated tests listed in `verbs.md`, `schema.md`, `validation.md` and `skills.md`, plus the import DAG |

Nothing runs against an on-disk instance except the fixture instance in `tests/cli/`, and no
test shells out except the one smoke test.

## Runner, tooling and wall time

pytest, dev group only; the athlete's install stays stdlib. ruff (lint and format) and pyright
in strict mode run in the same `uv run` step. One GitHub Actions workflow runs the three on
every push and pull request. No pre-commit framework.

The whole suite runs in under ten seconds on a laptop. A guard fails any single test that takes
longer than one second, so a slow test is fixed where it is written rather than tolerated. The
old suite's eleven minutes against on-disk instances is the anti-pattern this budget rules out.
