"""A store whose catalogue was seeded before the muscle registry lost `cardio` and `full_body`."""

import sqlite3

from coach.store.catalogue import seed_catalogue
from coach.store.chain import ENGINE
from coach.store.connection import connect

FULL_BODY = '{"primary":["full_body"],"secondary":[]}'
CARDIO = '{"primary":["cardio"],"secondary":[]}'
CARDIO_AND_CALVES = '{"primary":["cardio"],"secondary":["calves"]}'
SEEDED_MUSCLES = {
    "burpee": FULL_BODY,
    "cycling": CARDIO,
    "elliptical": CARDIO,
    "jump_rope": CARDIO_AND_CALVES,
    "mountain_climber": FULL_BODY,
    "rowing_machine": CARDIO,
    "running": CARDIO,
    "stationary_bike": CARDIO,
    "treadmill": CARDIO,
}


def a_store_seeded_at(version: int) -> sqlite3.Connection:
    conn = connect(":memory:")
    conn.executescript(ENGINE.ddl(version))
    conn.execute(f"PRAGMA user_version = {version}")
    with conn:
        seed_catalogue(conn)
        for id_, muscles in SEEDED_MUSCLES.items():
            conn.execute("UPDATE exercise SET muscles = ? WHERE id = ?", (muscles, id_))
    return conn
