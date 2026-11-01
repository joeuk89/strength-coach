# strength-coach
Strength coach engine: a ground-up rebuild of claude-strength-coach. Code owns invariants, the agent owns coaching judgement.

## Development

```
uv sync
uv run pytest
```

`uv run ruff check .`, `uv run ruff format --check .` and `uv run pyright` are the other checks CI runs.

## Engine and plugin from this checkout

```
uv tool install --editable .
```

puts `coach` and `coach-hook` on PATH. In Claude Code, `/plugin marketplace add <this checkout>`
then `/plugin install coach@strength-coach` adds the skills and the two hooks.
