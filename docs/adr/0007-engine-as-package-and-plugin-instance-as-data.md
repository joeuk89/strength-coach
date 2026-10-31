---
status: accepted
date: 2026-10-26
amended: 2026-10-31 by wayfinder #43 (four asked verbs; `init` on a `.dev` build needs `--pin`; the Hevy deny is every method on `/v1/workouts*`; the drift warning is `generated_file_drift`); 2026-10-31 by wayfinder #44 (the missing-install line is a shell guard in the hook declaration; two `uv` installs, one per job)
---

# The engine ships as one repo that is both a Python package and a Claude Code plugin; an instance holds only data

This repo is a `pyproject.toml` package whose entry point is `coach` (also `python3 -m coach`)
and, in the same tree, a Claude Code plugin carrying the skills and hooks. One git tag `vX.Y.Z`
versions both. An athlete installs the engine with `uv tool install` and `/plugin install`, then
runs `coach init` in an empty directory. The instance repo never contains framework files: no
skills, no hook wiring, no engine code. Chosen because the old `/framework-sync` copied 42k
lines of engine into each data repo (the review's root problem 7), and because ADR 0002 names
hosts beyond Claude Code (hooks, cron, a human terminal) that a plugin alone cannot reach.

## Considered options

- **Package and plugin from one repo (chosen).** The package puts `coach` on PATH for every
  host; the plugin is the only way to ship skills and hooks without copying them. Cost: two
  install lines and a version check between them.
- **Package only, with skills copied in by `coach init` and `coach upgrade`.** `/framework-sync`
  again, just smaller: the instance would hold framework files that drift and get edited.
- **Plugin only, running the engine from the plugin cache.** Nothing to install, but `coach` is
  off PATH for a terminal and cron, the cache path changes per version, and the engine would
  assume Claude Code is the only host.

## Consequences

- **Versioning.** Semver. Patch: no schema or skill-contract change. Minor: new verbs or skills,
  additive migrations. Major: the committed export changes shape so an older engine cannot
  import it. Releases are tags on `main`; the tag is also the plugin version.
- **The instance pins the engine.** `coach.toml` carries `[engine] version = "X.Y.Z"`. Every
  verb compares it to its own version first; a mismatch is exit 5 with the two versions and the
  way out. Exact match, no ranges. A `.dev` build of the engine (an editable install) matches
  any pin with the warning `engine_pin_dev` in the envelope, so unreleased code can run against
  a real instance. The pin itself is always a release: `init` on a `.dev` build refuses unless
  `--pin X.Y.Z` names the release the instance will run, and only `upgrade` on a release build
  rewrites `[engine]`, so `engine_pin_dev` clears by `upgrade` and by nothing else
  (`docs/spec/verbs.md`).
- **`coach upgrade`** is one of the four asked verbs, beside `plan apply`, `publish` and
  `init`, each declared `writes: hevy` or `git` and each with a `--dry-run` (ADR 0002). After the
  human has installed the newer engine and plugin, it checks the tree is clean, runs the schema
  migrations, rewrites the export, bumps the pin, regenerates `.claude/settings.json` and the
  instance CLAUDE.md, and commits. It refuses if the installed engine is older than the pin.
  Across a major it prints the migration notes before asking. No ordinary verb migrates
  implicitly: a schema behind the engine is exit 5 until `upgrade` runs.
- **Permission rules live in the instance**, because a plugin cannot ship them. `coach init`
  and `coach upgrade` generate them from the verb declarations: allow `coach`, ask on every verb
  declared `writes: hevy` or `git`, deny every method on `/v1/workouts*` as a second line behind
  the hook (ADR 0011). `coach status` warns `generated_file_drift` on drift between the file and
  what it would generate (`docs/spec/validation.md`); nothing rewrites the file outside
  `upgrade`.
- **Hooks are declared once**, in the plugin, and call `coach-hook <event>` (a second console
  entry point beside `coach`, not one of its leaves; ADR 0019): SessionStart and
  PreToolUse on Bash, nothing else in v1 (the old PostToolUse hash guard went with the parity
  checklist). The hook is the engine, so the engine cannot report its own absence: each hook
  declaration is a one-line shell guard, `command -v coach-hook >/dev/null && coach-hook <event>
  || echo "coach engine not installed: uv tool install ..."`, which prints that line and exits 0
  when the package is missing, so a missing install never blocks a session.
- **Skills live only in the plugin.** The instance CLAUDE.md is short and generated. A local
  change to a skill is a branch of the engine, never an edit in the instance.
- **Instance root** is the nearest ancestor of the cwd holding `coach.toml`, found the way git
  finds a repo. No env var, no flag; not inside one is exit 5. Several instances on one machine
  (real, simulated personas, a fixture) share one installed engine.
- **The repo is its own marketplace**: `.claude-plugin/marketplace.json` lists one plugin, at
  the root. Until the repo is public the marketplace is added from the local checkout, which is
  also the dev route: `uv tool install --editable .` for the `coach` and `coach-hook` on PATH,
  `uv sync` for the dev group the suite runs under, plus the local marketplace (ADR 0019).
- **Visibility.** This repo stays private until the week-boundary cutover, then goes public the
  same day the two old repos are archived and the old template's README points here.
- **The public template survives as `coach init` plus the README**, not as a repo to clone.
  v1 is one athlete per instance and nothing hard-codes the author, but other athletes are not
  a v1 acceptance test.
- **Python floor 3.12**, stdlib only. `uv` is the supported installer; `pip` works from the
  same file but is undocumented.
