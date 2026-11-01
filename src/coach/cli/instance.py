import sqlite3
import tomllib
from pathlib import Path
from typing import cast

from coach.cli.declaration import Instance
from coach.core.errors import Setup
from coach.store.connection import open_store

CONFIG = "coach.toml"


def find_root(start: Path) -> Path:
    """The nearest ancestor holding `coach.toml`, found the way git finds a repo (ADR 0007)."""
    for directory in (start, *start.parents):
        if (directory / CONFIG).is_file():
            return directory
    raise Setup("no_instance", f"no {CONFIG} in {start} or any directory above it")


def read_pin(root: Path) -> str:
    path = root / CONFIG
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise Setup("config_unknown_key", f"{path} is not valid TOML: {error}") from error
    engine: object = config.get("engine")
    version = cast(dict[str, object], engine).get("version") if isinstance(engine, dict) else None
    if not isinstance(version, str):
        raise Setup("engine_pin_mismatch", f"{path} has no [engine] version to pin the engine to")
    return version


def open_instance_store(instance: Instance) -> sqlite3.Connection:
    instance.store_path.parent.mkdir(exist_ok=True)
    return open_store(instance.store_path)
