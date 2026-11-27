"""What the athlete calls each session and exercise, the one lookup every page and message that
names them reads."""

from coach.core.pages import PageNames
from coach.core.program.form import Session
from coach.store import exercises, niggles, programs
from coach.store.connection import Connection
from coach.store.programs import VersionRow


def page_names(conn: Connection) -> PageNames:
    return PageNames(
        sessions={s.id: s.title for s in authored_sessions(conn, programs.latest(conn)).values()},
        exercises={str(row["id"]): str(row["name"]) for row in exercises.every(conn)},
    )


def authored_sessions(conn: Connection, version: VersionRow | None) -> dict[str, Session]:
    """Every session as the version names it, rehab sessions included."""
    found = {s.id: s for s in niggles.every_rehab_session(conn)}
    if version is not None:
        found |= {s.id: s for s in version.form.sessions}
    return found
