"""What the athlete calls each session and exercise, the one lookup every page and message that
names them reads."""

from collections.abc import Sequence

from coach.core.pages import PageNames
from coach.core.program.form import Session
from coach.store import exercises, niggles, programs
from coach.store.connection import Connection
from coach.store.programs import VersionRow
from coach.store.rows import Row


def page_names(conn: Connection, library: Sequence[Row] | None = None) -> PageNames:
    """`library` is the exercise rows when the caller has read them already."""
    rows = exercises.every(conn) if library is None else library
    return PageNames(
        sessions={s.id: s.title for s in authored_sessions(conn, programs.latest(conn)).values()},
        exercises={str(row["id"]): str(row["name"]) for row in rows},
    )


def authored_sessions(conn: Connection, version: VersionRow | None) -> dict[str, Session]:
    """Every session as the version names it, rehab sessions included."""
    found = {s.id: s for s in niggles.every_rehab_session(conn)}
    if version is not None:
        found |= {s.id: s for s in version.form.sessions}
    return found
