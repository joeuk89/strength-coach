from collections.abc import Mapping
from pathlib import Path

from coach.core.errors import Setup
from coach.github.client import TOKEN_NAME
from coach.hevy.client import KEY_NAME


def hevy_key(env: Mapping[str, str], dotenv: Path) -> str:
    """The Hevy API key (ADR 0011, "The client")."""
    key = find_secret(KEY_NAME, env, dotenv)
    if key is not None:
        return key
    raise Setup(
        "hevy_key_missing",
        f"no {KEY_NAME} in the environment or in {dotenv}; set it to your Hevy API key",
    )


def github_token(env: Mapping[str, str], dotenv: Path) -> str:
    """The token `report` files issues with (docs/spec/voice.md, "Reporting")."""
    token = find_secret(TOKEN_NAME, env, dotenv)
    if token is not None:
        return token
    raise Setup(
        "github_token_missing",
        f"no {TOKEN_NAME} in the environment or in {dotenv}; the report is not sent",
    )


def find_secret(name: str, env: Mapping[str, str], dotenv: Path) -> str | None:
    """The secret `name` from the environment, else from `.env`."""
    for value in (env.get(name), _from_dotenv(name, dotenv)):
        if value and value.strip():
            return value.strip()
    return None


def _from_dotenv(name: str, path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for raw in text.splitlines():
        line = raw.strip().removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None
