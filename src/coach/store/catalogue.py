import sqlite3
from importlib.resources import files

from coach.store.jsonl import load_rows


def seed_catalogue(conn: sqlite3.Connection) -> int:
    """Insert the engine catalogue into a new store (`schema.md`, "The engine catalogue")."""
    text = files("coach.store").joinpath("catalogue.jsonl").read_text(encoding="utf-8")
    return load_rows(conn, "exercise", text)
