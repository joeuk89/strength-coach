---
status: accepted
date: 2026-10-31
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
`store`, `hevy` and `cli`. Exactly three things are injected: a bare `sqlite3.Connection`, a
`HevyClient` protocol and a `Clock` protocol. Hooks reach the engine through a second console
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
  and `[dependency-groups] dev` with pytest, ruff and pyright. `uv tool install --editable .` is
  the dev route.
- **Import rule.** `core` imports stdlib and `core` only, and never `sqlite3`, I/O, the network or
  the current time; dates arrive as values. `store`, `hevy` and `render` import `core`.
  `services` imports those four. `cli` imports anything. `render` never imports `store`.
  `kit` (the plate-pool snapshot fetch) is a module beside `hevy`, not a seventh package. The
  four typed errors (`Refused`, `Invalid`, `Unreachable`, `Setup`) live where every layer can
  raise them, and only `cli` maps them to exit codes.
- **Seams.** `HevyClient` is a `typing.Protocol` of the allow-listed writes and the GETs;
  `hevy/client.py` and the test fake both satisfy it. `Clock` has `today()` and `now()`; the
  audit's timestamps come from it. Services take both as parameters from `cli`; `core` takes
  neither.
- **Hooks.** The plugin's hook declarations call `coach-hook session-start` and
  `coach-hook pre-tool-use`. ADR 0007's `coach hook <event>` is read as this entry point. It is
  absent from `--help`, `schema`, the sixteen-leaf count and the generated permission rules.
- **Test pyramid.** `tests/core/` (values, no database, the bulk), `tests/services/` (`:memory:`
  from `schema.sql` through scenario builders, `FakeHevy`, a fixed clock), `tests/cli/`
  (in-process `main(argv, env, stdout, stderr)` per exit class, the fixture instance, one
  subprocess smoke test of the installed `coach --help`), `tests/contract/` (the generated tests
  the spec lists, plus the import DAG).
- **Budget.** The whole suite runs in under ten seconds locally; a guard fails any single test
  over one second. One GitHub Actions workflow runs ruff, pyright strict and pytest on every push
  and pull request through `uv run`. No pre-commit framework.
- **Where the spec stops.** The module split inside each package, builder and fixture names, the
  CI file and the porting order from the old `coach/` are the first build ticket's own calls.
