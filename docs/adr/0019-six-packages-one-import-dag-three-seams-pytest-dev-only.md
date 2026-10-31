---
status: accepted
date: 2026-10-31
amended: 2026-10-31 by wayfinder #44 (the Write audit is the `HevyClient`'s own work, not a fourth seam; the plate-pool fetch is `cli`'s and its parse is `core`'s; the 429 retry sits below the protocol; seven test layers; `main` takes a client factory and a clock; the TOML emitter lives in `render`; the smoke test names its interpreter)
---

# The engine is six packages on one import DAG, with three injected seams; the suite is pytest, dev-only, under ten seconds

The `coach` package has six sub-packages, each one layer of "functional core, imperative shell":
`core` (pure functions, frozen values, the code registries), `store` (`schema.sql`, the
connection factory, migrations, row-to-value reads and writes), `hevy` (the allow-listed client
and its payload parsing), `render` (pages and Drafts as text), `services` (one module per verb
leaf, the transaction boundary) and `cli` (declarations, argv, envelope, exit codes, instance
root, `.env`, git, filesystem, hooks). Imports run one way, `core` ← `store`, `hevy`, `render`
← `services` ← `cli`, and a contract test walks every module with `ast` and fails on any other
edge or on `sqlite3`, `urllib`, `os`, `pathlib`, `subprocess` or the system clock outside
`store`, `hevy` and `cli`. Exactly three things are injected into a service: a bare
`sqlite3.Connection`, a `HevyClient` protocol and a `Clock` protocol. The Hevy write audit is
the client's own work behind that protocol, so it adds no seam. Hooks reach the engine through a second console
entry point, `coach-hook <event>`, not a leaf of `coach`. The runtime stays stdlib-only; pytest,
ruff and pyright are a `uv` dev dependency group. The spec is `docs/spec/testing.md`.

## Context

ADR 0002 fixed a CLI over plain service functions taking a connection and a clock, ADR 0003 a
pure `prescribe`, ADR 0007 a `src`-less sketch of one repo as package and plugin, ADR 0018 a
`schema.sql` copied byte for byte, and the 2026-10-26 review "functional core, imperative shell".
None said where the seams fall, what may import what, or how the suite is laid out. The old
`coach/` was about 80 flat modules and 69k lines with no import rule, and its 116-file
`unittest` suite took eleven minutes against on-disk instances. The athlete's standing bar for
the rebuild is clean, modular, maintainable and extendible code (KISS, SOLID).

## Considered options

- **Six packages, DAG enforced by a test, three injected seams (chosen).** The seams are the
  places where two adapters exist today: file or `:memory:` for the store, the real client or
  `FakeHevy` for Hevy, the system or a fixed date for the clock. Nothing else varies, so nothing
  else gets an abstraction. The import test makes the architecture a failing test rather than a
  convention a reviewer has to remember.
- **A repository or storage interface over SQLite.** Rejected: one adapter is a hypothetical
  seam. Services take the connection and call `store` functions; swapping the file for
  `:memory:` is the same adapter.
- **Flat package with naming conventions.** Rejected: the old engine's shape. Nothing stops a
  scheme reading the database.
- **`unittest` so even development is stdlib-only.** Rejected: "stdlib only" is a rule for the
  athlete's install, and the suite never ships. pytest buys plain `assert`, fixtures for the
  in-memory store and the fake client, and parametrised generated contract tests.
- **`coach hook <event>` as a seventeenth leaf, or hidden.** Rejected: `verbs.md` caps the tree
  at sixteen and its contract test says "no more"; a hidden leaf would be a special case in
  `--help`, `schema` and the permission rules. A second entry point shares `cli` internals and
  touches none of them.

## Consequences

- **Layout.** `src/coach/` with `__main__.py` so `python3 -m coach` works, `tests/` beside it,
  plugin files (`.claude-plugin/`, `skills/`, `hooks/`) at the repo root. `pyproject.toml`
  declares two scripts, `coach` and `coach-hook`, zero runtime dependencies, Python 3.12 floor,
  and `[dependency-groups] dev` with pytest, ruff and pyright. Two installs, each for one job:
  `uv tool install --editable .` puts `coach` and `coach-hook` on PATH for the instances on the
  machine, and `uv sync` in the checkout creates the dev environment that `uv run pytest`, ruff
  and pyright use. The suite never depends on the first: its one subprocess smoke test runs
  `[sys.executable, "-m", "coach", "--help"]`, the interpreter running the suite, never the
  `coach` on PATH.
- **Import rule.** `core` imports stdlib and `core` only, and never `sqlite3`, I/O, the network or
  the current time; dates arrive as values. `store`, `hevy` and `render` import `core`.
  `services` imports those four. `cli` imports anything. `render` never imports `store`.
  The kit splits along the same line: `core/kit.py` parses a `kit/<name>.achievable.json`
  document into enumerated racks and is pure; `cli` reads the committed file and the inventory's
  hash and hands both to the service as values (ADR 0021), so a service test at a plate-pool
  location reads `tests/fixtures/kit/` and nothing else. No `kit` module sits beside `hevy`, no
  fetch of kit exists anywhere, and no module outside `store`, `hevy` and `cli` imports
  `urllib`. The
  four typed errors (`Refused`, `Invalid`, `Unreachable`, `Setup`) live where every layer can
  raise them, and only `cli` maps them to exit codes.
- **Seams.** `HevyClient` is a `typing.Protocol` of the four allow-listed writes, the GETs
  `import` and `plan apply` need, and `open_audit()`; `hevy/client.py` and the test fake both
  satisfy it. Each write method takes a `WriteContext` value (WeekPlan id, Write plan hash,
  routine id) beside its body. `Clock` has `today()` and `now()`, in the athlete's timezone:
  `cli` builds it from `[athlete].timezone` and passes it to every service and to the real
  client. Services take connection, client and clock as parameters from `cli`; `core` takes
  none of them. What the real client is built with (the API key, the audit path, the clock, a
  `urllib` opener and a sleeper that default to the real ones) are its constructor's arguments,
  used by `tests/hevy/` to record requests and refuse the network; they are the adapter's own
  wiring, not seams, and no service sees them.
- **Write audit.** The real client writes `hevy/writes.jsonl` itself: `open_audit()` opens the
  file for append and raises `Refused` (`audit_unwritable`) when it cannot, which `plan apply`
  calls before its first live GET; every write method appends one request line before the
  request is sent and one response line when the attempt ends, after any retries, with the
  status or the error; the verify lines follow the read-back. `FakeHevy` keeps the same lines
  in a list a test reads. The 429 retry (sleep 30 s, three tries) lives inside
  `hevy/client.py` below the protocol, so the fake has no 429 fault and `Clock` has no sleeper.
- **Entry point.** `main(argv, env, stdout, stderr, *, make_client=..., clock=None) -> int`:
  the two keyword-only arguments default to the real client factory and the system clock built
  from the instance's timezone, and `tests/cli/` passes a `FakeHevy` factory and a fixed clock,
  so a CLI test of `import` or `plan apply` runs with Hevy on.
- **TOML.** The stdlib reads TOML (`tomllib`) and writes none, so `render/toml.py` is the one
  emitter, covering the subset `coach.toml` and the two Drafts use (tables, arrays of tables,
  strings including multi-line, integers, floats, booleans, dates, arrays). `init` writes
  `coach.toml` through it from `cli`; `plan draft` and `program show --draft` through
  `services`. A `tests/render/` test round-trips every emitted document through `tomllib`.
  Zero runtime dependencies stands.
- **Hooks.** The plugin's hook declarations call `coach-hook session-start` and
  `coach-hook pre-tool-use`. ADR 0007's `coach hook <event>` is read as this entry point. It is
  absent from `--help`, `schema`, the sixteen-leaf count and the generated permission rules.
- **Test pyramid.** Seven directories, one per package plus contract: `tests/core/` (values, no
  database, the bulk), `tests/store/` (migrations, the rebuild, row round-trips), `tests/hevy/`
  (payload parsing from the fixture shapes, the real client against a recording opener: the
  allow-list, the retry, the audit lines), `tests/render/` (page determinism, the check-in
  renderer, the 40-line prompt, the TOML round-trip), `tests/services/` (`:memory:` from
  `schema.sql` through scenario builders, `FakeHevy`, a fixed clock), `tests/cli/` (in-process
  `main` per exit class with the fixture instance, a `FakeHevy` factory and a fixed clock; the
  one subprocess smoke test), `tests/contract/` (the generated tests the spec lists, the 3 KB
  envelope test, the `rn:` registry test, the import DAG).
- **Budget.** The whole suite runs in under ten seconds locally; a guard fails any single test
  over one second. One GitHub Actions workflow runs ruff, pyright strict and pytest on every push
  and pull request through `uv run`. No pre-commit framework.
- **Where the spec stops.** The module split inside each package, builder and fixture names, the
  CI file and the porting order from the old `coach/` are the first build ticket's own calls.
