# strength-coach
Strength coach engine: a ground-up rebuild of claude-strength-coach. Code owns invariants, the agent owns coaching judgement.

## Development

```
uv sync
uv run pytest
```

`uv run ruff check .`, `uv run ruff format --check .` and `uv run pyright` are the other checks CI runs.
