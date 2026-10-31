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

Two explicit exceptions, both in `tests/contract/`, both registry tests that check a document
exists in the shape a code constant names and never what it says:

- The test that the engine's `schema.sql` is byte-identical to the SQL blocks of
  `docs/spec/schema.md` reads that document. The DDL is hand-written and hand-copied, and this
  test is what keeps the copy honest; the test that every CHECK list equals its code registry
  guards the other direction.
- The `rn:` registry test (ADR 0004, ADR 0020) walks every `rn` constant in the `core`
  registries (flags, schemes, the phase and week tables) and resolves each to a numbered claim
  or a numbered section heading of the note under `docs/spec/` that `research-notes.md` lists.
  It reads headings and claim numbers, never the claim's text, and nothing at runtime reads a
  note.

No third exception is added without amending this paragraph.

`docs/spec/parity.md` is the 2026-10-26 review of the old system's behaviours. It is reference,
not a test source: later decisions changed or dropped many of its rows, and where they differ
the spec documents and ADRs win. No test cites a parity row.

## Fixtures

Most tests build their own history with scenario builders: small Python functions
(`a_program_with(...)`, `exposures_for(line, weeks=...)`, `a_niggle(...)`) that write into an
in-memory SQLite database created from `schema.sql`. A builder writes only through `store`
functions, never with its own `INSERT`, so every state a test starts from is one the engine can
produce and a schema change breaks the builder where the engine would break. Each test states
exactly the history it needs and nothing else. No real athlete data enters the engine
repository.

Three committed fixture directories cover what builders cannot:

- `tests/fixtures/instance/`: one complete synthetic **Fixture instance**, laid out as an
  instance looks after `init`, the onboarding writes (`profile.md`, a Goal and a Phase through
  `goal adopt`, a first Program version) and one `publish` (`export/` with its manifest,
  `pages/`). It is generated, not typed: a committed script under `tests/support/` builds it
  through `store` functions and the `publish` service, and regenerating it is how it changes.
  Used by the import, export round-trip and CLI envelope tests, and by the contract test that
  holds every default envelope under 3 KB (`verbs.md`). For that test to mean anything the
  instance must overflow every list a default summary truncates: more than ten exposures per
  lift, more than ten flags on the plan in force, more than ten routines, more than ten ledger
  rows of each kind, more than ten readings per kind, so every `truncated` is true at least
  once. It is still small: a year of one program, not a career.
- `tests/fixtures/hevy/`: a handful of anonymised Hevy GET responses (a workout page, a routine,
  a folder, an exercise template). They fix the payload shapes the parser must accept and feed
  the parser tests only.
- `tests/fixtures/kit/`: one synthetic kit tables document, `<name>.achievable.json` with its
  header, and the inventory it hashes against. It feeds the `core/kit.py` parser tests and every
  service test that rounds at a plate-pool location, including the `kit_tables_stale` refusal
  (ADR 0021).

## The fake Hevy

Hevy is tested against one in-process fake client, `FakeHevy`, holding routines, folders,
templates and workouts in memory. It satisfies `HevyClient` and nothing more: the four
allow-listed writes (ADR 0011), the GETs the protocol declares (workout events and pages,
routines, folders, exercise templates, body measurements) and `open_audit()`; it has no method
for any other endpoint, so a service that wanted one fails by construction. Like Hevy, it drops
routine-level notes on PUT. A test can tell it to move a routine's `updated_at`, fail the next
GET, or return a read-back that differs from the PUT. It keeps the audit lines the real client
would write in a list the test reads. It has no 429 fault: the retry lives inside
`hevy/client.py`, below the protocol, and is tested there.

The real client is tested in `tests/hevy/` with its constructor arguments: a recording opener
that refuses to open any connection, a sleeper that records instead of sleeping, a fixed clock
and an audit path under `tmp_path`. That is where the allow-list regression test runs (a
non-allow-listed method raises before the opener is called), the 429 retry (three attempts,
two recorded 30 s sleeps, no real time), the key scrub and the audit's two lines per request.
No HTTP, no cassette files, no network in the suite.

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
bar is the three targets written there: under 10 `coach` calls, under 8k tokens of engine-owned
instructions (the athlete's own global CLAUDE.md is outside the count) and zero Bash calls with
inline Python per check-in plus programming pass. It is measured on the first
two real weekly passes after cutover and at each later milestone, each as a dated row in the
table. A miss opens an issue. Cutover is gated by the green suite at the pinned engine tag and
the acceptance check, nothing else.

## Package layout

One repo is the package and the plugin (ADR 0007). `pyproject.toml` at the root declares the
`coach` package under `src/`, two console scripts (`coach` and `coach-hook`), no runtime
dependencies, a Python 3.12 floor, and a `dev` dependency group holding pytest, ruff and
pyright. Two installs: `uv tool install --editable .` puts `coach` and `coach-hook` on PATH for
the instances on this machine, and `uv sync` in the checkout makes the dev environment that
`uv run pytest`, `uv run ruff` and `uv run pyright` use. The suite needs only the second.

```
pyproject.toml
src/coach/
  __main__.py          python3 -m coach
  core/                pure functions, frozen values, the code registries; kit.py parses the kit tables
  store/               schema.sql, connection factory, migrations, reads and writes
  hevy/                HevyClient protocol, the allow-listed client with its audit and retry, payload parsing
  render/              pages and Drafts as text; toml.py, the one TOML emitter
  services/            one module per verb leaf
  cli/                 declarations, argv, envelope, exit codes, root, .env, git, hooks, the plate-pool fetch
tests/
  core/  store/  hevy/  render/  services/  cli/  contract/
  fixtures/instance/  fixtures/hevy/  fixtures/kit/
  support/             scenario builders, FakeHevy, fixed clock, the fixture-instance generator
.claude-plugin/  skills/  hooks/
```

The split inside each package, the builder and fixture names and the CI file are the first
build ticket's calls.

## Module seams

Six packages, one import direction (ADR 0019):

| Package | Owns | May import |
| --- | --- | --- |
| `core` | schemes, e1RM, return bands, week kind, units, loads and rounding, the eight-step `prescribe` pipeline (ADR 0017), validation rules, the registries (`schemes`, `flags`, `record-kinds`, `views`) with their `rn` constants, the kit tables parser (`kit.py`) | stdlib, `core` |
| `store` | `schema.sql` (byte-identical to `schema.md`) and the frozen DDL of each past version, the catalogue seed, the connection factory with `foreign_keys` on, the rebuild from the export, migrations, functions that read rows into `core` values and write values as rows | `core` |
| `hevy` | the `HevyClient` protocol, the real client over `urllib` with the allow-list, the 429 retry and the Write audit, payload parsing from the fixture shapes | `core` |
| `render` | `pages/*` and the plan and program Drafts, as text from `core` values; `toml.py`, the one TOML emitter (`coach.toml` and both Drafts) | `core` |
| `services` | one function per leaf: load a snapshot through `store`, run `core`, write in one transaction, return a typed result or raise `Refused`, `Invalid`, `Unreachable` or `Setup` | `core`, `store`, `hevy`, `render` |
| `cli` | verb declarations, argv parsing, the envelope, exit-code mapping, instance-root discovery, `.env`, git, filesystem, reading `kit/` and hashing the inventory, the Clock built from `[athlete].timezone`, the `coach-hook` commands | everything |

`core` never imports `sqlite3`, `urllib`, `os`, `pathlib`, `subprocess` or reads the current
time; dates arrive as values. `render` never imports `store`. A contract test walks every module
with `ast` and fails on any other edge.

Three things are injected into a service, because each has two adapters:

- **The store**: a bare `sqlite3.Connection`, a file in the instance or `:memory:` in a test. No
  repository interface; `store` is a module of functions and the service chooses the
  transaction boundary.
- **Hevy**: `HevyClient`, a `typing.Protocol` of the four allow-listed writes (ADR 0011), the
  GETs `import` and `plan apply` need, and `open_audit()`. Each write takes a `WriteContext`
  (WeekPlan id, Write plan hash, routine id) beside its body. `hevy/client.py` and
  `tests/support/fake_hevy.py` both satisfy it. The Write audit is the client's own work: the
  real one appends to `hevy/writes.jsonl` (a request line before each send, a response line
  after the attempt ends, verify lines after each read-back), the fake keeps the same lines in
  memory. So the audit needs no filesystem in `services` and no fourth seam.
- **The clock**: `Clock`, a protocol with `today()` and `now()` in the athlete's timezone.
  Services take it; `cli` builds it from `[athlete].timezone` and passes it to every service
  and to the real client, whose audit timestamps come from it. It has no sleeper: the 429 wait
  is the real client's, below the protocol.

What the real client is constructed with (key, audit path, clock, opener, sleeper) is the
adapter's wiring, varied only by `tests/hevy/`; it is not a seam and no service sees it. The
`import` service takes the plate-pool document as a value the `cli` command fetched, so a
service test hands it the fixture file.

The entry point is `main(argv, env, stdout, stderr, *, make_client=..., clock=None) -> int`.
The keyword-only arguments default to the real client factory and the system clock; `tests/cli/`
passes a `FakeHevy` factory and a fixed clock, so a CLI test can run `import` and `plan apply`
with Hevy on.

## The test pyramid

Seven directories, one per package plus contract:

| Layer | Runs against | Covers |
| --- | --- | --- |
| `tests/core/` | values only, no database | schemes, the pipeline, bands, rounding, validation, registries, the kit parser on `fixtures/kit/`; the bulk of the suite |
| `tests/store/` | `:memory:` and `tmp_path` files | the connection factory and `foreign_keys`, every migration from each frozen DDL under `schema_history/`, the rebuild from an export, row-to-value round-trips |
| `tests/hevy/` | the real client with a recording, refusing opener, a recording sleeper, a fixed clock, an audit file under `tmp_path`; `fixtures/hevy/` | payload parsing, the allow-list raising before any request, the 429 retry, the key scrub, the audit's two lines per request and the verify lines, `audit_unwritable` |
| `tests/render/` | `core` values | page determinism (ADR 0012: the same store, the same bytes), the check-in record renderer (`check-in.md`), the 40-line approval prompt (ADR 0006), the TOML emitter round-trip through `tomllib` |
| `tests/services/` | `:memory:` built from `schema.sql` through scenario builders, `FakeHevy`, a fixed clock, the kit fixture as a value | each leaf's behaviour, transactions, refusals, idempotent re-runs |
| `tests/cli/` | in-process `main` with a `FakeHevy` factory and a fixed clock; the fixture instance | one test per exit class, `init`, `import` with Hevy on and off, `plan apply` end to end, the export round-trip; one subprocess smoke test that `[sys.executable, "-m", "coach", "--help"]` exits 0 |
| `tests/contract/` | the declarations, `schema.sql`, the registries, the skill files, the research notes' headings, the source tree, the fixture instance | the generated tests listed in `verbs.md`, `schema.md`, `validation.md` and `skills.md`, the 3 KB envelope test, the `rn:` registry test, the import DAG |

The 3 KB envelope test lives in `tests/contract/` only. Nothing runs against an on-disk instance
except the fixture instance, and no test shells out except the one smoke test, which runs the
interpreter the suite runs under, never the `coach` on PATH.

## Runner, tooling and wall time

pytest, dev group only; the athlete's install stays stdlib. ruff (lint and format) and pyright
in strict mode run in the same `uv run` step. One GitHub Actions workflow runs the three on
every push and pull request. No pre-commit framework.

The whole suite runs in under ten seconds on a laptop. A guard fails any single test that takes
longer than one second, so a slow test is fixed where it is written rather than tolerated. The
old suite's eleven minutes against on-disk instances is the anti-pattern this budget rules out.
