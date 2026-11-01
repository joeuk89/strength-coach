from collections.abc import Mapping
from pathlib import Path

from coach.core.errors import Setup

KEY_NAME = "HEVY_API_KEY"


def api_key(env: Mapping[str, str], dotenv: Path) -> str:
    """The Hevy API key from the environment, else from `.env` (ADR 0011, "The client")."""
    for value in (env.get(KEY_NAME), _from_dotenv(dotenv)):
        if value and value.strip():
            return value.strip()
    raise Setup(
        "hevy_key_missing",
        f"no {KEY_NAME} in the environment or in {dotenv}; set it to your Hevy API key",
    )


def _from_dotenv(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for raw in text.splitlines():
        line = raw.strip().removeprefix("export ").strip()
        name, sep, value = line.partition("=")
        if sep and name.strip() == KEY_NAME:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None
