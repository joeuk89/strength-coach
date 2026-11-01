# Strength coach engine

A ground-up rebuild of `claude-strength-coach`. The code owns invariants (arithmetic, units, kit rounding, safety bounds, data integrity, Hevy shape); the agent owns coaching judgement with a recorded reason.

The engine is in `src/coach/`, the plugin's skills in `skills/` and its hooks in `hooks/`. The spec is `GLOSSARY.md`, `docs/adr/` and `docs/spec/`, and the code follows it. Work goes through GitHub issues, one branch and PR per issue.

**Hard constraint:** existing Hevy workout history is never modified or deleted, by any code or agent, ever. Adding new workouts is allowed.

This file is for working on the engine. Each athlete's instance gets its own generated `CLAUDE.md` from `src/coach/cli/generated.py`; change that one there, not here.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, driven with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
