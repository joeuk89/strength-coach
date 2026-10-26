# Strength coach engine

A ground-up rebuild of `claude-strength-coach`. The code owns invariants (arithmetic, units, kit rounding, safety bounds, data integrity, Hevy shape); the agent owns coaching judgement with a recorded reason.

The rebuild is being charted on the wayfinder map, issue #1. Work it with `/wayfinder 1`. Until the map closes, this repo holds the spec: `GLOSSARY.md`, `docs/adr/` and `docs/spec/`.

**Hard constraint:** existing Hevy workout history is never modified or deleted, by any code or agent, ever. Adding new workouts is allowed.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, driven with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
