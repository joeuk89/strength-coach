import sqlite3

from coach.core.mirror import FolderRole, MirroredFolder, MirroredRoutine

# schema.md, "Updated in place": the two Hevy mirrors are overwritten per Hevy id, never deleted.


def upsert_routine(conn: sqlite3.Connection, routine: MirroredRoutine, imported_at: str) -> bool:
    """Write the routine when it is new or differs; True when a row changed."""
    stored = conn.execute(
        "SELECT updated_at, title, folder_id, raw FROM routine WHERE hevy_id = ?",
        (routine.hevy_id,),
    ).fetchone()
    if stored == (routine.updated_at, routine.title, routine.folder_id, routine.raw):
        return False
    conn.execute(
        "INSERT INTO routine (hevy_id, updated_at, title, folder_id, raw, imported_at)"
        " VALUES (?,?,?,?,?,?) ON CONFLICT (hevy_id) DO UPDATE SET"
        " updated_at = excluded.updated_at, title = excluded.title,"
        " folder_id = excluded.folder_id, raw = excluded.raw, imported_at = excluded.imported_at",
        (
            routine.hevy_id,
            routine.updated_at,
            routine.title,
            routine.folder_id,
            routine.raw,
            imported_at,
        ),
    )
    return True


def upsert_folder(conn: sqlite3.Connection, folder: MirroredFolder) -> bool:
    """Write the folder's role row when it is new or differs; True when a row changed. A Hevy id
    another role already holds is left where it is."""
    holder = conn.execute("SELECT role FROM folder WHERE hevy_id = ?", (folder.hevy_id,)).fetchone()
    if holder is not None and holder[0] != folder.role:
        return False
    stored = conn.execute(
        "SELECT hevy_id, title FROM folder WHERE role = ?", (folder.role,)
    ).fetchone()
    if stored == (folder.hevy_id, folder.title):
        return False
    conn.execute(
        "INSERT INTO folder (role, hevy_id, title) VALUES (?,?,?) ON CONFLICT (role) DO UPDATE"
        " SET hevy_id = excluded.hevy_id, title = excluded.title",
        (folder.role, folder.hevy_id, folder.title),
    )
    return True


def routines(conn: sqlite3.Connection) -> tuple[MirroredRoutine, ...]:
    return tuple(
        MirroredRoutine(*row)
        for row in conn.execute(
            "SELECT hevy_id, updated_at, title, folder_id, raw FROM routine ORDER BY hevy_id"
        )
    )


def folders(conn: sqlite3.Connection) -> tuple[MirroredFolder, ...]:
    rows: list[tuple[FolderRole, str, str]] = conn.execute(
        "SELECT role, hevy_id, title FROM folder ORDER BY role"
    ).fetchall()
    return tuple(MirroredFolder(*row) for row in rows)
