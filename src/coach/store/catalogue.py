import json
import sqlite3
from importlib.resources import files

from coach.store.jsonl import load_rows


def seed_catalogue(conn: sqlite3.Connection) -> int:
    """Insert the engine catalogue into a new store (`schema.md`, "The engine catalogue")."""
    return load_rows(conn, "exercise", _catalogue())


def merge_catalogue(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Insert each catalogue id the store lacks and return them; a row the store has may carry
    the athlete's edit or a verified template id, so it is never touched."""
    have = {found for (found,) in conn.execute("SELECT id FROM exercise")}
    missing = [line for line in _catalogue().splitlines() if line.strip() and _id(line) not in have]
    load_rows(conn, "exercise", "\n".join(missing))
    return tuple(_id(line) for line in missing)


def _catalogue() -> str:
    return files("coach.store").joinpath("catalogue.jsonl").read_text(encoding="utf-8")


def _id(line: str) -> str:
    return json.loads(line)["id"]
